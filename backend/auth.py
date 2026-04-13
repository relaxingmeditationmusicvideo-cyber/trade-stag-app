"""
Trade Stag — Minimal auth module.

Uses:
  - SQLite for user storage (tradestag.db in backend/ directory)
  - bcrypt for password hashing (via passlib)
  - PyJWT for token signing

⚠️ SECURITY NOTE:
  - Hardcoded JWT_SECRET below is OK for local dev only.
    In production, read from os.environ["JWT_SECRET"] and rotate regularly.
  - This is a minimal auth implementation, NOT production-hardened.
    Before launch, add: rate limiting, password reset flow, email verification,
    MFA, audit logging, account lockout after failed attempts.

See SEBI_COMPLIANCE.md before charging users for access.
"""

from __future__ import annotations

import os
import sqlite3
import secrets
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("tradestag.auth")

# ─── Configuration ────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET") or "dev-secret-CHANGE-ME-" + secrets.token_hex(8)
JWT_ALGO = "HS256"
JWT_EXPIRES_DAYS = 30

DB_PATH = Path(__file__).parent / "tradestag.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Database ────────────────────────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create users table if it doesn't exist."""
    conn = _get_db()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT UNIQUE NOT NULL,
            name         TEXT,
            password_hash TEXT NOT NULL,
            plan         TEXT DEFAULT 'free',
            disclaimer_ack_at TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            last_login_at TEXT
        )
        """)
        conn.commit()
        logger.info(f"✅ Auth DB ready at {DB_PATH}")
    finally:
        conn.close()

# Run on import so main.py doesn't have to remember
init_db()

# ─── Password hashing ────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    try:
        return pwd_context.verify(pw, pw_hash)
    except Exception:
        return False

# ─── JWT ─────────────────────────────────────────────────────────────
def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRES_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ─── User CRUD ───────────────────────────────────────────────────────
def get_user_by_email(email: str) -> Optional[dict]:
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_user_by_id(uid: int) -> Optional[dict]:
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_user(email: str, password: str, name: str = "") -> dict:
    conn = _get_db()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                (email.lower().strip(), (name or "").strip(), hash_password(password)),
            )
            conn.commit()
            uid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="An account with this email already exists")
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def touch_last_login(uid: int):
    conn = _get_db()
    try:
        conn.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (uid,))
        conn.commit()
    finally:
        conn.close()

def _public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name") or "",
        "plan": u.get("plan") or "free",
        "created_at": u.get("created_at"),
    }

# ─── FastAPI dependency: extract current user from Authorization header ──
def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    uid = int(payload.get("sub", 0))
    user = get_user_by_id(uid)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user

# ─── Pydantic request models ────────────────────────────────────────
class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = ""

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

# ─── Router ─────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup")
def signup(body: SignupBody):
    # Validate email length
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = create_user(body.email, body.password, body.name or "")
    token = create_token(user["id"], user["email"])
    touch_last_login(user["id"])
    logger.info(f"New signup: {user['email']}")
    return {"token": token, "user": _public_user(user)}

@router.post("/login")
def login(body: LoginBody):
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"])
    touch_last_login(user["id"])
    return {"token": token, "user": _public_user(user)}

@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user)}

@router.post("/logout")
def logout():
    # JWT is stateless — client just drops the token.
    # If you later add a blocklist or session table, revoke it here.
    return {"ok": True}

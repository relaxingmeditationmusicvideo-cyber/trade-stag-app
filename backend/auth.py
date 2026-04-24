"""
Trade Stag — Auth module with subscription tiers & payment integration.

Uses:
  - SQLite for user storage (tradestag.db in backend/ directory)
  - bcrypt for password hashing (via passlib)
  - PyJWT for token signing
  - Razorpay for payment processing
  - SMTP for email notifications

Plans:
  - free:    10-day trial, 3 core screeners, market pulse, no stock deep-dive
  - pro:     Rs 499/month — all screeners, stock detail, sector analytics
  - premium: Rs 1499/month — everything in pro + future features

Owner email bypasses all restrictions (full access, no payment required).

Environment variables needed for production:
  JWT_SECRET         — random secret for signing tokens
  OWNER_EMAIL        — owner email (defaults to relaxingmeditationmusicvideo@gmail.com)
  RAZORPAY_KEY_ID    — Razorpay API key
  RAZORPAY_KEY_SECRET— Razorpay API secret
  SMTP_HOST          — SMTP server (default: smtp.gmail.com)
  SMTP_PORT          — SMTP port (default: 587)
  SMTP_USER          — SMTP username / email
  SMTP_PASS          — SMTP password / app password
  NOTIFY_EMAIL       — email to receive notifications (default: OWNER_EMAIL)
"""

from __future__ import annotations

import os
import sqlite3
import secrets
import logging
import smtplib
import hashlib
import hmac
import json
import threading
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger("tradestag.auth")

# ─── Configuration ────────────────────────────────────────────────────
JWT_SECRET = os.environ.get("JWT_SECRET") or "dev-secret-CHANGE-ME-" + secrets.token_hex(8)
JWT_ALGO = "HS256"
JWT_EXPIRES_DAYS = 30

DB_PATH = Path(__file__).parent / "tradestag.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─── Owner & Plan config ─────────────────────────────────────────────
OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "relaxingmeditationmusicvideo@gmail.com").lower().strip()
TRIAL_DAYS = 10

# Razorpay
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

# SMTP config for email notifications
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", OWNER_EMAIL)

# Plan feature definitions
# Free: 3 core screeners only
FREE_SCANNERS = {"all", "aplus", "trade"}
# Pro: all scanners
PRO_FEATURES = {"all_scanners", "stock_detail", "sectors", "score_breakdown", "csv_export"}
# Premium: everything + future features
PREMIUM_FEATURES = PRO_FEATURES | {"historical_scans", "watchlists", "api_access", "priority_support"}

# ─── Database ────────────────────────────────────────────────────────
def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create users table if it doesn't exist, migrate new columns."""
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

        # ── Migration: add new subscription columns if missing ──
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}

        # NOTE: SQLite ALTER TABLE only allows constant defaults, not expressions
        # like datetime('now'). So we add columns with no default, then backfill.
        migrations = {
            "trial_start": "TEXT",
            "plan_expires": "TEXT",
            "razorpay_sub_id": "TEXT",
            "razorpay_customer_id": "TEXT",
            "approved": "INTEGER DEFAULT 0",
        }
        for col, col_def in migrations.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_def}")
                logger.info(f"  Migrated: added column '{col}'")

        # Backfill trial_start for existing users who don't have it
        conn.execute("UPDATE users SET trial_start = created_at WHERE trial_start IS NULL")
        # Auto-approve the owner
        conn.execute("UPDATE users SET approved = 1 WHERE LOWER(email) = ?", (OWNER_EMAIL,))
        conn.commit()

        # ── Payments table ──
        conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            razorpay_order_id TEXT,
            razorpay_payment_id TEXT,
            razorpay_signature TEXT,
            plan            TEXT NOT NULL,
            amount          INTEGER NOT NULL,
            currency        TEXT DEFAULT 'INR',
            status          TEXT DEFAULT 'created',
            created_at      TEXT DEFAULT (datetime('now')),
            verified_at     TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)
        conn.commit()

        logger.info(f"Auth DB ready at {DB_PATH}")
    finally:
        conn.close()

# Run on import so main.py doesn't have to remember
init_db()

# ─── Email notifications (fire-and-forget in background thread) ──────
def _send_email_bg(subject: str, body_html: str, to_email: str = None):
    """Send email notification in a background thread. Silently fails if SMTP not configured."""
    if not SMTP_USER or not SMTP_PASS:
        logger.info(f"Email skipped (SMTP not configured): {subject}")
        return

    def _send():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Trade Stag <{SMTP_USER}>"
            msg["To"] = to_email or NOTIFY_EMAIL
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            logger.info(f"Email sent: {subject}")
        except Exception as e:
            logger.warning(f"Email send failed: {e}")

    threading.Thread(target=_send, daemon=True).start()


def notify_owner_signup(user_email: str, user_name: str):
    """Notify owner when a new user signs up — includes approve link."""
    _send_email_bg(
        subject=f"Trade Stag — New Signup (APPROVAL NEEDED): {user_email}",
        body_html=f"""
        <div style="font-family:sans-serif;max-width:500px;">
            <h2 style="color:#059669;">New User Signup — Approval Required</h2>
            <p><strong>Email:</strong> {user_email}</p>
            <p><strong>Name:</strong> {user_name or '(not provided)'}</p>
            <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
            <p><strong>Status:</strong> <span style="color:#f59e0b;font-weight:bold;">Pending Approval</span></p>
            <hr style="border:none;border-top:1px solid #333;" />
            <p style="font-size:14px;">To approve this user, go to your
            <a href="https://www.tradestag.com/app/admin" style="color:#06b6d4;">Admin Panel</a>
            and click Approve.</p>
            <p style="color:#888;font-size:12px;">Trade Stag Notification System</p>
        </div>
        """,
    )


def notify_owner_login(user_email: str, user_name: str):
    """Notify owner when a user signs in."""
    _send_email_bg(
        subject=f"Trade Stag — User Login: {user_email}",
        body_html=f"""
        <div style="font-family:sans-serif;max-width:500px;">
            <h2 style="color:#06b6d4;">User Login</h2>
            <p><strong>Email:</strong> {user_email}</p>
            <p><strong>Name:</strong> {user_name or '(not provided)'}</p>
            <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
            <hr style="border:none;border-top:1px solid #333;" />
            <p style="color:#888;font-size:12px;">Trade Stag Notification System</p>
        </div>
        """,
    )


def notify_owner_payment(user_email: str, plan: str, amount: int):
    """Notify owner when a user makes a payment."""
    _send_email_bg(
        subject=f"Trade Stag — Payment Received: {user_email} → {plan}",
        body_html=f"""
        <div style="font-family:sans-serif;max-width:500px;">
            <h2 style="color:#f59e0b;">Payment Received!</h2>
            <p><strong>Email:</strong> {user_email}</p>
            <p><strong>Plan:</strong> {plan.capitalize()}</p>
            <p><strong>Amount:</strong> Rs {amount/100}</p>
            <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
            <hr style="border:none;border-top:1px solid #333;" />
            <p style="color:#888;font-size:12px;">Trade Stag Notification System</p>
        </div>
        """,
    )


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
                "INSERT INTO users (email, name, password_hash, plan, trial_start) VALUES (?, ?, ?, 'free', datetime('now'))",
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

def update_user_plan(uid: int, plan: str, expires: str = None, razorpay_sub_id: str = None):
    """Update user's plan after successful payment."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE users SET plan = ?, plan_expires = ?, razorpay_sub_id = ? WHERE id = ?",
            (plan, expires, razorpay_sub_id, uid),
        )
        conn.commit()
    finally:
        conn.close()


def is_owner(email: str) -> bool:
    """Check if the user is the app owner."""
    return email.lower().strip() == OWNER_EMAIL


def get_plan_status(user: dict) -> dict:
    """Compute the effective plan status for a user.
    Returns: { plan, is_owner, is_trial, trial_days_left, trial_expired, is_active }
    """
    email = (user.get("email") or "").lower().strip()

    # Owner bypasses everything
    if is_owner(email):
        return {
            "plan": "premium",
            "effective_plan": "premium",
            "is_owner": True,
            "is_trial": False,
            "trial_days_left": 999,
            "trial_expired": False,
            "is_active": True,
        }

    approved = bool(user.get("approved", 0))

    # If not approved by admin, user is in "pending" state — no access
    if not approved:
        return {
            "plan": "free",
            "effective_plan": "pending",
            "is_owner": False,
            "is_trial": False,
            "trial_days_left": 0,
            "trial_expired": False,
            "is_active": False,
            "approved": False,
        }

    # Approved users get full premium access
    return {
        "plan": "premium",
        "effective_plan": "premium",
        "is_owner": False,
        "is_trial": False,
        "trial_days_left": 999,
        "trial_expired": False,
        "is_active": True,
        "approved": True,
    }


def _public_user(u: dict) -> dict:
    """Return user info safe for the frontend, including plan status."""
    plan_status = get_plan_status(u)
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name") or "",
        "plan": plan_status["plan"],
        "effective_plan": plan_status["effective_plan"],
        "is_owner": plan_status["is_owner"],
        "is_trial": plan_status["is_trial"],
        "trial_days_left": plan_status["trial_days_left"],
        "trial_expired": plan_status["trial_expired"],
        "is_active": plan_status["is_active"],
        "approved": plan_status.get("approved", bool(u.get("approved", 0))),
        "plan_expires": u.get("plan_expires"),
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

# ─── Razorpay helpers ────────────────────────────────────────────────
def _razorpay_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make authenticated request to Razorpay API."""
    import urllib.request
    import base64

    url = f"https://api.razorpay.com/v1{endpoint}"
    auth_str = base64.b64encode(f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}".encode()).decode()

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Basic {auth_str}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"Razorpay API error: {e}")
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {e}")


def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature using HMAC SHA256."""
    if not RAZORPAY_KEY_SECRET:
        logger.warning("Razorpay secret not configured — skipping signature check")
        return False
    msg = f"{order_id}|{payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─── Pydantic request models ────────────────────────────────────────
class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = ""

class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class CreateOrderBody(BaseModel):
    plan: str = Field(..., pattern="^(pro|premium)$")

class VerifyPaymentBody(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

# ─── Router ─────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/signup")
def signup(body: SignupBody):
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = get_user_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = create_user(body.email, body.password, body.name or "")
    token = create_token(user["id"], user["email"])
    touch_last_login(user["id"])
    logger.info(f"New signup: {user['email']}")

    # Notify owner
    notify_owner_signup(user["email"], user.get("name", ""))

    return {"token": token, "user": _public_user(user)}

@router.post("/login")
def login(body: LoginBody):
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"])
    touch_last_login(user["id"])

    # Notify owner (skip if owner is logging in themselves)
    if not is_owner(body.email):
        notify_owner_login(user["email"], user.get("name", ""))

    return {"token": token, "user": _public_user(user)}

@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": _public_user(user)}

@router.get("/plan")
def get_plan(user: dict = Depends(get_current_user)):
    """Return detailed plan status for the current user."""
    status = get_plan_status(user)
    return {
        "user_email": user["email"],
        **status,
        "free_scanners": list(FREE_SCANNERS),
        "razorpay_key": RAZORPAY_KEY_ID,  # Public key, safe to expose
    }

@router.post("/create-order")
def create_order(body: CreateOrderBody, user: dict = Depends(get_current_user)):
    """Create a Razorpay order for plan upgrade."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(status_code=503, detail="Payment gateway not configured. Please contact support.")

    # Owner doesn't need to pay
    if is_owner(user["email"]):
        update_user_plan(user["id"], body.plan, (datetime.utcnow() + timedelta(days=36500)).isoformat())
        return {"status": "owner_bypass", "user": _public_user(get_user_by_id(user["id"]))}

    amount = 49900 if body.plan == "pro" else 149900  # In paise (Rs 499 / Rs 1499)

    order_data = _razorpay_request("POST", "/orders", {
        "amount": amount,
        "currency": "INR",
        "receipt": f"ts_{user['id']}_{body.plan}_{int(datetime.utcnow().timestamp())}",
        "notes": {
            "user_id": str(user["id"]),
            "user_email": user["email"],
            "plan": body.plan,
        },
    })

    # Save order in payments table
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO payments (user_id, razorpay_order_id, plan, amount, status) VALUES (?, ?, ?, ?, 'created')",
            (user["id"], order_data["id"], body.plan, amount),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "order_id": order_data["id"],
        "amount": amount,
        "currency": "INR",
        "key": RAZORPAY_KEY_ID,
        "plan": body.plan,
        "user_email": user["email"],
        "user_name": user.get("name") or "",
    }

@router.post("/verify-payment")
def verify_payment(body: VerifyPaymentBody, user: dict = Depends(get_current_user)):
    """Verify Razorpay payment and activate plan."""
    # Verify signature
    if not verify_razorpay_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment verification failed — invalid signature")

    # Find the order in our payments table
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM payments WHERE razorpay_order_id = ? AND user_id = ?",
            (body.razorpay_order_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")

        payment = dict(row)
        plan = payment["plan"]
        amount = payment["amount"]

        # Mark payment as verified
        conn.execute(
            "UPDATE payments SET razorpay_payment_id = ?, razorpay_signature = ?, status = 'paid', verified_at = datetime('now') WHERE id = ?",
            (body.razorpay_payment_id, body.razorpay_signature, payment["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    # Activate plan — 30 days from now
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()
    update_user_plan(user["id"], plan, expires)

    # Notify owner
    notify_owner_payment(user["email"], plan, amount)

    updated_user = get_user_by_id(user["id"])
    return {
        "status": "success",
        "plan": plan,
        "expires": expires,
        "user": _public_user(updated_user),
    }

@router.post("/logout")
def logout():
    # JWT is stateless — client just drops the token.
    return {"ok": True}


# ─── Admin endpoints (owner only) ──────────────────────────────────
def _require_owner(user: dict):
    """Raise 403 if the user is not the owner."""
    if not is_owner(user.get("email", "")):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/admin/users")
def admin_list_users(user: dict = Depends(get_current_user)):
    """List all users with approval status. Owner only."""
    _require_owner(user)
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, email, name, plan, approved, created_at, last_login_at, trial_start FROM users ORDER BY created_at DESC"
        ).fetchall()
        users = []
        for r in rows:
            u = dict(r)
            u["approved"] = bool(u.get("approved", 0))
            u["is_owner"] = is_owner(u["email"])
            users.append(u)
        return {"users": users, "total": len(users)}
    finally:
        conn.close()


class ApproveBody(BaseModel):
    user_id: int


@router.post("/admin/approve")
def admin_approve_user(body: ApproveBody, user: dict = Depends(get_current_user)):
    """Approve a user — gives them full premium access."""
    _require_owner(user)
    conn = _get_db()
    try:
        target = conn.execute("SELECT * FROM users WHERE id = ?", (body.user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        conn.execute("UPDATE users SET approved = 1, plan = 'premium' WHERE id = ?", (body.user_id,))
        conn.commit()
        logger.info(f"Admin approved user: {dict(target)['email']}")

        # Notify the approved user
        target_dict = dict(target)
        _send_email_bg(
            subject="Trade Stag — Your Account Has Been Approved!",
            body_html=f"""
            <div style="font-family:sans-serif;max-width:500px;">
                <h2 style="color:#059669;">Account Approved!</h2>
                <p>Hi {target_dict.get('name') or 'there'},</p>
                <p>Your Trade Stag account has been approved. You now have full access to all scanners and features.</p>
                <p><a href="https://www.tradestag.com/login" style="color:#06b6d4;font-weight:bold;">Log in now →</a></p>
                <hr style="border:none;border-top:1px solid #333;" />
                <p style="color:#888;font-size:12px;">Trade Stag — Smart Screening for Indian Markets</p>
            </div>
            """,
            to_email=target_dict["email"],
        )

        return {"ok": True, "message": f"User {target_dict['email']} approved"}
    finally:
        conn.close()


@router.post("/admin/reject")
def admin_reject_user(body: ApproveBody, user: dict = Depends(get_current_user)):
    """Reject/revoke a user's access."""
    _require_owner(user)
    conn = _get_db()
    try:
        target = conn.execute("SELECT * FROM users WHERE id = ?", (body.user_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="User not found")
        target_dict = dict(target)
        if is_owner(target_dict["email"]):
            raise HTTPException(status_code=400, detail="Cannot reject the owner account")
        conn.execute("UPDATE users SET approved = 0, plan = 'free' WHERE id = ?", (body.user_id,))
        conn.commit()
        logger.info(f"Admin rejected user: {target_dict['email']}")
        return {"ok": True, "message": f"User {target_dict['email']} access revoked"}
    finally:
        conn.close()

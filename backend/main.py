"""
Trade Stag — FastAPI Backend
Wraps the Trade Stag v7.1 engine as REST API endpoints.

Usage:
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000

Endpoints:
  GET /api/market-pulse     → Market overview (indices, VIX, FII/DII, PCR, breadth)
  GET /api/screener         → All analyzed stocks with grades, scores, signals
  GET /api/stock/{symbol}   → Detailed single stock analysis
  GET /api/top-trades       → Top conviction opportunities
  GET /api/sectors          → Sector momentum rankings
  GET /api/scan             → Trigger fresh scan (POST)
  GET /api/status           → Scan status & last update time
"""

import os, sys, json, time, threading
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trade-stag")

app = FastAPI(
    title="Trade Stag API",
    description="Trade Stag — NSE 500 Scanner — India First",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Auth routes ───
try:
    from auth import router as auth_router
    app.include_router(auth_router)
    logger.info("✅ Auth routes loaded (/api/auth/signup, /api/auth/login)")
except ImportError as e:
    logger.warning(f"⚠️ Auth module not loaded: {e}")

# ─── In-memory store for scan results ───
_store = {
    "results": [],
    "market_pulse": {},
    "top_trades": [],
    "sectors": [],
    "breadth": {},
    "fii_dii": {},
    "pcr": {},
    "max_pain": {},
    "last_scan": None,
    "scan_running": False,
    "scan_progress": 0,
    "scan_total": 0,
    "error": None,
}

# ─── Persistence: save/load scan results to disk so they survive restarts ───
# Render free-tier filesystem is ephemeral, but this still helps when the
# process restarts within the same instance (common between sleeps/deploys).
import json as _json
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "scan_cache.json")

_PERSISTED_KEYS = [
    "results", "market_pulse", "top_trades", "sectors",
    "breadth", "fii_dii", "pcr", "max_pain", "last_scan",
]

def _save_cache():
    """Save scan results to disk after a successful scan."""
    try:
        payload = {k: _store.get(k) for k in _PERSISTED_KEYS}
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            _json.dump(payload, f, default=str)
        logger.info(f"💾 Cached scan results to {_CACHE_FILE}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to save cache: {e}")

def _load_cache():
    """Load previously cached scan results. Returns True if loaded."""
    try:
        if not os.path.exists(_CACHE_FILE):
            return False
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            payload = _json.load(f)
        if not payload or not payload.get("results"):
            return False
        for k in _PERSISTED_KEYS:
            if k in payload:
                _store[k] = payload[k]
        logger.info(f"📂 Loaded cached scan: {len(_store.get('results') or [])} stocks, last_scan={_store.get('last_scan')}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to load cache: {e}")
        return False

# Universe cap — limits Render-triggered scans to fit 512MB free-tier RAM.
# Primary data source is scan_cache.json (pushed from local `run_scan.py`).
# If a scan IS triggered on Render, cap to 150 to avoid OOM.
_SCAN_UNIVERSE_LIMIT = int(os.environ.get("SCAN_UNIVERSE_LIMIT", "150"))

# ─── Import the analyzer engine ───
# The analyzer is placed alongside this file as `analyzer.py`
# (copy your nse500_swing_analyzer_vikrant.py and rename it)
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from analyzer import (
        NSESession, NSEDataFetcher, NSEAnalysisPipeline,
        IndiaVIXFetcher, FIIDIIFetcher, MaxPainCalculator,
        SECTOR_MAP, FNO_STOCKS, CFG
    )
    ANALYZER_AVAILABLE = True
    logger.info("✅ Analyzer engine loaded successfully")
except ImportError as e:
    ANALYZER_AVAILABLE = False
    logger.warning(f"⚠️  Analyzer engine not found: {e}")
    logger.warning("   Place your analyzer.py (renamed from nse500_swing_analyzer_vikrant.py) in the backend/ folder")


def _g(obj, *keys, default=None):
    """Get value from obj by trying multiple key/attribute names (case-insensitive)."""
    for k in keys:
        # dict lookup
        if isinstance(obj, dict):
            if k in obj:
                v = obj[k]
                if v is not None:
                    return v
            # case-insensitive dict lookup
            for dk in obj.keys():
                if str(dk).lower() == k.lower():
                    v = obj[dk]
                    if v is not None:
                        return v
        # object attribute lookup
        if hasattr(obj, k):
            v = getattr(obj, k)
            if v is not None and not callable(v):
                return v
        # dataclass / to_dict
        if hasattr(obj, "__dict__"):
            d = obj.__dict__
            if k in d and d[k] is not None:
                return d[k]
    return default


def _f(v, d=0.0):
    """Safe float coercion."""
    if v is None: return d
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):  # NaN/Inf
            return d
        return f
    except Exception:
        return d


def _i(v, d=0):
    try: return int(_f(v, d))
    except Exception: return d


def _b(v):
    """Safe bool coercion."""
    if isinstance(v, bool): return v
    if v in (None, "", 0, "0", "false", "False", "no"): return False
    return bool(v)


def _s(v, d="—"):
    if v is None: return d
    s = str(v).strip()
    return s if s else d


def _normalize_stock(raw):
    """Convert analyzer's full stock dict into a uniform JSON-safe dict
    matching the field shape consumed by the React frontend."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        # Convert object to dict
        raw = getattr(raw, "__dict__", {}) or {}
    try:
        # Signals list
        signals_raw = raw.get("active_signals") or raw.get("signals") or []
        if not isinstance(signals_raw, list):
            signals_raw = [signals_raw]
        signals = [str(s) for s in signals_raw if s is not None]

        # Score breakdown — keep top items for tooltip
        sb = raw.get("score_breakdown") or {}
        if not isinstance(sb, dict): sb = {}
        # Sort score components by value desc, take top 4 for tooltip
        sb_top = sorted([(k, _f(v)) for k, v in sb.items() if _f(v) > 0],
                        key=lambda x: x[1], reverse=True)[:4]

        # Trade setup
        ts = raw.get("trade_setup") or {}
        if not isinstance(ts, dict): ts = {}

        # Sparkline (last ~20 close prices)
        spark = raw.get("sparkline") or []
        if not isinstance(spark, list): spark = []
        spark = [_f(v) for v in spark][:30]

        # Bulk deal info
        bd = raw.get("bulk_deal") or {}
        if not isinstance(bd, dict): bd = {}

        # Earnings info
        ei = raw.get("earnings_info") or {}
        if not isinstance(ei, dict): ei = {}

        # Weekly summary
        wk = raw.get("weekly") or {}
        if not isinstance(wk, dict): wk = {}

        # Compute derived flags from analyzer fields
        grade = _s(raw.get("grade"), "?")
        rs_pct = _f(raw.get("rs_percentile"))
        delivery_pct = _f(raw.get("delivery_pct"))
        vol_ratio = _f(raw.get("vol_ratio"))
        chg_1d = _f(raw.get("chg_1d"))
        chg_5d = _f(raw.get("chg_5d"))

        normalized = {
            # Core
            "symbol": _s(raw.get("symbol"), ""),
            "name": _s(raw.get("name") or raw.get("company_name") or raw.get("symbol"), ""),
            "sector": _s(raw.get("sector"), "Others"),
            "grade": grade,
            "grade_color": _s(raw.get("grade_color"), ""),
            "score": _f(raw.get("score")),

            # Price
            "price": _f(raw.get("price")),
            "open": _f(raw.get("open")),
            "high": _f(raw.get("high")),
            "low": _f(raw.get("low")),
            "volume": _i(raw.get("volume")),
            "avg_vol_20d": _i(raw.get("avg_vol_20d")),
            "vol_ratio": vol_ratio,

            # Returns
            "chg_1d": chg_1d,
            "chg_5d": chg_5d,
            "chg_1m": _f(raw.get("chg_1m")),
            "chg_3m": _f(raw.get("chg_3m")),

            # 52-week
            "high_52w": _f(raw.get("high_52w")),
            "low_52w": _f(raw.get("low_52w")),
            "pct_from_high": _f(raw.get("pct_from_high")),

            # Indicators
            "rsi": _f(raw.get("rsi")),
            "adx": _f(raw.get("adx")),
            "di_plus": _f(raw.get("di_plus")),
            "di_minus": _f(raw.get("di_minus")),
            "macd": _f(raw.get("macd")),
            "macd_signal": _f(raw.get("macd_sig")),
            "macd_hist": _f(raw.get("macd_hist")),
            "bb_width": _f(raw.get("bb_width")),
            "atr_pct": _f(raw.get("atr_pct")),
            "stoch_k": _f(raw.get("stoch_k")),
            "obv_trend": _s(raw.get("obv_trend"), "—"),
            "mfi": _f(raw.get("mfi")),
            "cmf": _f(raw.get("cmf")),

            # EMAs
            "ema_5": _f(raw.get("ema_5")),
            "ema_10": _f(raw.get("ema_10")),
            "ema_13": _f(raw.get("ema_13")),
            "ema_21": _f(raw.get("ema_21")),
            "ema_26": _f(raw.get("ema_26")),
            "ema_50": _f(raw.get("ema_50")),
            "ema_200": _f(raw.get("ema_200")),
            "above_200ema": _b(raw.get("above_200ema")),

            # EMA scanner flags
            "ema_early_momentum": _b(raw.get("ema_early_momentum")),
            "ema_fresh_cross_5_13": _b(raw.get("ema_fresh_cross_5_13")),
            "ema_swing_confirm": _b(raw.get("ema_swing_confirm")),
            "ema_near_20_pullback": _b(raw.get("ema_near_20_pullback")),
            "ema_golden_cross": _b(raw.get("ema_golden_cross")),
            "ema_fresh_golden_cross": _b(raw.get("ema_fresh_golden_cross")),
            "ema_ultra_pro": _b(raw.get("ema_ultra_pro")),
            "near_20d_high": _b(raw.get("near_20d_high")),

            # Patterns / signals (booleans)
            "vcp_score": _f(raw.get("vcp_score")),
            "breakout": _b(raw.get("breakout")),
            "breakout_str": _s(raw.get("breakout_str"), ""),
            "pocket_pivot": _b(raw.get("pocket_pivot")),
            "nr7": _b(raw.get("nr7")),
            "nr4": _b(raw.get("nr4")),
            "inside_day": _b(raw.get("inside_day")),
            "vol_dry_up": _b(raw.get("vol_dry_up")),
            "flat_base": _b(raw.get("flat_base")),
            "obv_divergence": _b(raw.get("obv_divergence")),
            "at_support": _b(raw.get("at_support")),
            "is_weekly_nr7": _b(raw.get("is_weekly_nr7")),
            "circuit_risk": _b(raw.get("circuit_risk")),
            "is_fno": _b(raw.get("is_fno")),
            "is_ipo_base": _b(raw.get("is_ipo_base")),
            "candle_score": _f(raw.get("candle_score")),

            # India-specific
            "promoter_buying": _b(raw.get("promoter_buying")),
            "promoter_selling": _b(raw.get("promoter_selling")),
            "promoter_chg_qoq": raw.get("promoter_chg_qoq"),
            "pledge_decreasing": _b(raw.get("pledge_decreasing")),
            "oi_buildup_type": _s(raw.get("oi_buildup_type"), ""),
            "oi_change_pct": _f(raw.get("oi_change_pct")),
            "india_vix": _f(raw.get("india_vix")),
            "fii_buying": _b(raw.get("fii_buying")),
            "supertrend_dir": _i(raw.get("supertrend_dir")),

            # Volume Surge
            "vol_surge_type": _s(raw.get("vol_surge_type"), ""),
            "vol_surge_ratio": _f(raw.get("vol_surge_ratio")),
            "vol_surge_up": _b(raw.get("vol_surge_up")),

            # Fundamentals
            "fund_score": _f(raw.get("fund_score")),
            "fund_grade": _s(raw.get("fund_grade"), "N/A"),
            "roe": raw.get("roe"),
            "roce": raw.get("roce"),
            "roic": raw.get("roic"),
            "de_ratio": raw.get("de_ratio"),
            "eps_growth": raw.get("eps_growth"),
            "rev_growth": raw.get("rev_growth"),
            "profit_margin": raw.get("profit_margin"),
            "operating_margin": raw.get("operating_margin") or raw.get("opm"),
            "pe_ratio": raw.get("pe_ratio"),
            "pb_ratio": raw.get("pb_ratio"),
            "market_cap": raw.get("market_cap"),

            # Promoter & Pledging
            "promoter_holding": raw.get("promoter_holding"),
            "pledge_pct": raw.get("pledge_pct"),
            "pledge_danger": _b(raw.get("pledge_danger")),
            "pledge_warn": _b(raw.get("pledge_warn")),

            # Stage Analysis
            "stage": _s(raw.get("stage"), "?"),
            "is_stage2": _b(raw.get("is_stage2")),

            # Institutional Accumulation
            "is_accumulating": _b(raw.get("is_accumulating")),
            "accum_days": _i(raw.get("accum_days")),
            "accum_score": _f(raw.get("accum_score")),
            "accum_label": _s(raw.get("accum_label"), "None"),
            "accum_signals": raw.get("accum_signals") or [],

            # Delivery & Earnings
            "delivery_pct": delivery_pct,
            "earnings_upcoming": _b(ei.get("has_upcoming")),
            "earnings_days": _i(ei.get("days_to_earnings")),
            "near_52w_high": _b(raw.get("near_52w_high")),

            # RS
            "rs_alpha": _f(raw.get("rs_alpha")),
            "rs_percentile": rs_pct,

            # Sector momentum
            "sector_strength": _f(raw.get("sector_strength")),
            "sector_rank": _i(raw.get("sector_rank")),

            # Expert Filter (v7)
            "expert_yes": _i(raw.get("expert_yes")),
            "expert_decision": _s(raw.get("expert_decision"), "—"),
            "confidence_pct": _f(raw.get("confidence_pct")),

            # Trade Setup
            "trade_setup": {
                "entry": _f(ts.get("entry") or ts.get("entry_price")),
                "stop_loss": _f(ts.get("stop_loss") or ts.get("sl")),
                "target_1": _f(ts.get("target_1") or ts.get("t1")),
                "target_2": _f(ts.get("target_2") or ts.get("t2")),
                "risk_reward": _f(ts.get("risk_reward") or ts.get("rr")),
                "qty": _i(ts.get("qty") or ts.get("quantity")),
            },

            # Score breakdown
            "score_breakdown": {k: _f(v) for k, v in sb.items()},
            "score_top": [{"name": k.replace("_", " "), "value": v} for k, v in sb_top],

            # Sparkline
            "sparkline": spark,

            # Active signals
            "active_signals": signals,

            # Bulk deal
            "bulk_deal_value": _f(bd.get("value")),
            "bulk_deal_type": _s(bd.get("type"), ""),

            # Weekly
            "weekly_rsi": _f(wk.get("w_rsi")),
            "weekly_adx": _f(wk.get("w_adx")),
        }

        # ── Computed scanner flags (used by frontend chips/scanners) ──
        # NOTE: Thresholds mirror the analyzer's own scanner definitions
        # (nse500_swing_analyzer_vikrant.py lines 8018-8036 and 3500-3549).
        fund_grade_val = normalized["fund_grade"]  # "Strong" / "Good" / "Moderate" / "Weak" / "N/A"
        pe = _f(raw.get("pe_ratio"))
        pb = _f(raw.get("pb_ratio"))
        roe = _f(raw.get("roe"))
        roce = _f(raw.get("roce"))
        roic = _f(raw.get("roic"))
        op_margin = _f(raw.get("operating_margin") or raw.get("opm"))
        mcap = _f(raw.get("market_cap"))
        rev_gr = _f(raw.get("rev_growth"))
        eps_gr = _f(raw.get("eps_growth"))
        de = _f(raw.get("de_ratio"))

        normalized["flag_rs_elite"] = rs_pct >= 90
        normalized["flag_hi_delivery"] = delivery_pct >= 55
        # Analyzer: vol_surges = [r for r in results if r.get("vol_surge_type") is not None]
        normalized["flag_vol_surge"] = bool(normalized["vol_surge_type"]) or normalized["vol_surge_up"] or vol_ratio >= 2.0
        normalized["flag_gainer"] = chg_1d > 0
        normalized["flag_loser"] = chg_1d < 0
        normalized["flag_gainer_5d"] = chg_5d > 0
        normalized["flag_aplus"] = grade in ("A+", "A")
        normalized["flag_strong_grade"] = grade in ("A+", "A", "B+")
        # Analyzer: fund_strong = [r for r in results if r.get("fund_grade") == "Strong"]
        normalized["flag_fund_strong"] = fund_grade_val in ("Strong", "Good")
        normalized["flag_breakout"] = normalized["breakout"]
        # Analyzer: vcps = [r for r in results if r["vcp_score"] >= 60]
        normalized["flag_vcp"] = normalized["vcp_score"] >= 60
        normalized["flag_nr7"] = normalized["nr7"]
        normalized["flag_inside_day"] = normalized["inside_day"]
        normalized["flag_pocket_pivot"] = normalized["pocket_pivot"]
        normalized["flag_vol_dryup"] = normalized["vol_dry_up"]
        normalized["flag_stage2"] = normalized["is_stage2"]
        normalized["flag_accumulation"] = normalized["is_accumulating"]
        normalized["flag_pledge_danger"] = normalized["pledge_danger"]
        normalized["flag_earnings_warn"] = normalized["earnings_upcoming"]
        normalized["flag_expert_pick"] = normalized["expert_decision"] in ("CONVICTION", "TRADE")
        normalized["flag_ema_scanner"] = (
            normalized["ema_early_momentum"] or normalized["ema_swing_confirm"]
            or normalized["ema_golden_cross"] or normalized["ema_ultra_pro"]
        )
        normalized["flag_price_action"] = (
            normalized["nr7"] or normalized["nr4"] or normalized["inside_day"]
            or normalized["pocket_pivot"] or normalized["flat_base"]
        )

        # ── Fundamental / Value / Quality screens (matches analyzer lines 3500-3549) ──
        # Value Screens
        flag_low_pe       = (pe is not None and 0 < pe < 15)
        flag_low_pb       = (pb is not None and 0 < pb < 1.5)
        flag_graham       = (pe is not None and pb is not None and pe > 0 and pb > 0 and (pe * pb) < 22.5)
        flag_magic_f      = (roic is not None and roic > 15 and pe is not None and 0 < pe < 20)
        flag_val_growth   = (pe is not None and 0 < pe < 25 and rev_gr is not None and rev_gr > 10)
        flag_underval_gr  = (pe is not None and 0 < pe < 20 and eps_gr is not None and eps_gr > 15)
        normalized["flag_value_screen"] = bool(
            flag_low_pe or flag_low_pb or flag_graham or flag_magic_f
            or flag_val_growth or flag_underval_gr
        )

        # Quality Screens
        flag_blue_chip    = (mcap is not None and mcap >= 50000)  # ≥ 50,000 Cr
        flag_coffee_can   = (roce is not None and roce > 15 and de is not None and de < 0.5)
        flag_high_opm     = (op_margin is not None and op_margin > 20)
        flag_qual_growth  = (roe is not None and roe > 15 and eps_gr is not None and eps_gr > 15)
        flag_large_cap_q  = (mcap is not None and mcap >= 20000 and fund_grade_val in ("Strong", "Good"))
        flag_mid_cap_q    = (mcap is not None and 5000 <= mcap < 20000 and fund_grade_val in ("Strong", "Good"))
        normalized["flag_quality_screen"] = bool(
            flag_blue_chip or flag_coffee_can or flag_high_opm
            or flag_qual_growth or flag_large_cap_q or flag_mid_cap_q
        )

        # ── New screener flags (v8 — competitive paid features) ──
        price = normalized["price"]
        low_52w = normalized["low_52w"]
        high_52w = normalized["high_52w"]
        pct_from_high = normalized["pct_from_high"]
        bb = normalized["bb_width"]

        # 52-Week Low Reversal: within 15% of 52w low, positive 5D momentum, volume support
        pct_from_low = ((price - low_52w) / low_52w * 100) if low_52w and low_52w > 0 else 999
        normalized["pct_from_low"] = round(pct_from_low, 2)
        normalized["flag_low_reversal"] = (
            pct_from_low <= 15
            and chg_5d > 0
            and vol_ratio >= 1.0
            and grade not in ("D", "F", "?")
        )

        # Delivery Spike: delivery% >= 60 AND vol_ratio >= 1.2 (institutional activity)
        normalized["flag_delivery_spike"] = (
            delivery_pct >= 60
            and vol_ratio >= 1.2
        )

        # Promoter Buying: promoters increasing stake
        normalized["flag_promoter_buying"] = bool(normalized.get("promoter_buying"))

        # Bollinger Squeeze: BB width < 8 (very tight bands, expansion imminent)
        normalized["flag_bb_squeeze"] = (
            bb > 0 and bb < 8
            and normalized["adx"] >= 15
        )

        # IPO Base Breakout: disabled — detect_ipo_base relies on len(df)
        # which only reflects fetched history (~250-300 rows), not actual
        # listing age.  Until we add a real listing-date lookup, keep False.
        normalized["flag_ipo_base"] = False

        # Volume Dry-Up + Pattern: vol dry-up coinciding with VCP, flat base, or NR7
        normalized["flag_dryup_pattern"] = (
            normalized["vol_dry_up"]
            and (normalized["vcp_score"] >= 45 or normalized["flat_base"] or normalized["nr7"])
        )

        # Near 52W High with momentum: within 5% of 52w high, strong volume
        normalized["flag_52w_breakout_zone"] = (
            pct_from_high is not None
            and abs(pct_from_high) <= 5
            and vol_ratio >= 1.2
            and chg_1d > 0
        )

        # RS Strong (70-90 percentile — broader than elite)
        normalized["flag_rs_strong"] = rs_pct >= 70 and rs_pct < 90

        # ── AVWAP Pre-Breakout Scanner (v8.0) ──
        normalized["avwap_score"]            = _i(raw.get("avwap_score"))
        normalized["avwap_value"]            = _f(raw.get("avwap_value"))
        normalized["avwap_above"]            = _b(raw.get("avwap_above"))
        normalized["avwap_held_days"]        = _i(raw.get("avwap_held_days"))
        normalized["avwap_dist_to_breakout"] = _f(raw.get("avwap_dist_to_breakout"))
        normalized["avwap_vol_vs_avg"]       = _f(raw.get("avwap_vol_vs_avg"))
        normalized["avwap_consolidation"]    = _b(raw.get("avwap_consolidation"))
        normalized["avwap_vol_contraction"]  = _b(raw.get("avwap_vol_contraction"))
        normalized["avwap_candidate"]        = _b(raw.get("avwap_candidate"))
        normalized["avwap_smart_money"]      = _b(raw.get("avwap_smart_money"))
        normalized["avwap_tag"]              = _s(raw.get("avwap_tag"), "")
        normalized["avwap_sma20"]            = _f(raw.get("avwap_sma20"))
        normalized["avwap_sma50"]            = _f(raw.get("avwap_sma50"))
        normalized["avwap_high_20d"]         = _f(raw.get("avwap_high_20d"))
        normalized["flag_avwap_breakout"]    = bool(
            normalized["avwap_score"] >= 3
            and normalized["avwap_above"]
        )

        # Chartink Scanner Flags
        _price = normalized.get("price", 0)
        _open = normalized.get("open", 0)
        _high = normalized.get("high", 0)
        _low = normalized.get("low", 0)
        _volume = normalized.get("volume", 0)
        _prev_close = _f(raw.get("prev_close"))
        _prev_high = _f(raw.get("prev_high"))
        _sma_20 = _f(raw.get("sma_20"))
        _sma_50 = _f(raw.get("sma_50"))
        _vol_sma_10 = _f(raw.get("vol_sma_10"))
        _vol_sma_20 = _f(raw.get("vol_sma_20"))
        _rsi = normalized.get("rsi", 0)
        _rsi_prev = _f(raw.get("rsi_prev"))
        _ema_200 = normalized.get("ema_200", 0)

        # Store extra fields for frontend display
        normalized["prev_close"] = _prev_close
        normalized["prev_high"] = _prev_high
        normalized["sma_20"] = _sma_20
        normalized["vol_sma_10"] = _vol_sma_10

        # 1. 2x Volume Bullish: volume > vol_sma_10 * 2 AND low > prev_close
        normalized["flag_vol_2x_bull"] = bool(
            _vol_sma_10 > 0 and _volume > _vol_sma_10 * 2
            and _prev_close > 0 and _low > _prev_close
        )

        # 2. 3x Volume Breakout: volume > vol_sma_10 * 3 AND close > prev_high
        normalized["flag_vol_3x_breakout"] = bool(
            _vol_sma_10 > 0 and _volume > _vol_sma_10 * 3
            and _prev_high > 0 and _price > _prev_high
        )

        # 3. Bullish Breakout with Volume: close > prev_high AND volume > vol_sma_20 * 1.5
        normalized["flag_bull_breakout_vol"] = bool(
            _prev_high > 0 and _price > _prev_high
            and _vol_sma_20 > 0 and _volume > _vol_sma_20 * 1.5
        )

        # 4. RSI 50 Cross with Volume: RSI crossed above 50 (rsi > 50 and rsi_prev <= 50) AND volume > vol_sma_20 * 1.5
        normalized["flag_rsi50_cross"] = bool(
            _rsi > 50 and _rsi_prev is not None and _rsi_prev > 0 and _rsi_prev <= 50
            and _vol_sma_20 > 0 and _volume > _vol_sma_20 * 1.5
        )

        # 5. 200 EMA Bullish Crossover: close crossed above ema_200 AND volume > vol_sma_20
        normalized["flag_ema200_cross"] = bool(
            _ema_200 > 0 and _price > _ema_200
            and _prev_close > 0 and _prev_close <= _ema_200
            and _vol_sma_20 > 0 and _volume > _vol_sma_20
        )

        # 6. 20 SMA Breakout: close crossed above sma_20 AND volume > vol_sma_10 * 1.5
        normalized["flag_sma20_breakout"] = bool(
            _sma_20 > 0 and _price > _sma_20
            and _prev_close > 0 and _prev_close <= _sma_20
            and _vol_sma_10 > 0 and _volume > _vol_sma_10 * 1.5
        )

        # 7. BTST Bullish: close > open AND close > prev_high AND volume > vol_sma_10 * 2
        normalized["flag_btst_bull"] = bool(
            _price > _open and _open > 0
            and _prev_high > 0 and _price > _prev_high
            and _vol_sma_10 > 0 and _volume > _vol_sma_10 * 2
        )

        # 8. Strong Intraday Momentum: close > open AND close > vwap (use typical price proxy) AND volume > vol_sma_20 * 2
        _typ_price = (_high + _low + _price) / 3 if _price > 0 else 0
        normalized["flag_strong_momentum"] = bool(
            _price > _open and _open > 0
            and _price > _typ_price
            and _vol_sma_20 > 0 and _volume > _vol_sma_20 * 2
        )

        # 9. Gap Up with Volume: open > prev_high AND volume > vol_sma_10 * 1.5
        normalized["flag_gap_up_vol"] = bool(
            _prev_high > 0 and _open > _prev_high
            and _vol_sma_10 > 0 and _volume > _vol_sma_10 * 1.5
        )

        # 10. Delivery Style Strong: close > open AND close > sma_20 AND volume > vol_sma_20 * 2
        normalized["flag_delivery_strong"] = bool(
            _price > _open and _open > 0
            and _sma_20 > 0 and _price > _sma_20
            and _vol_sma_20 > 0 and _volume > _vol_sma_20 * 2
        )

        # 11. Beginner Scanner: close > prev_high AND volume > vol_sma_10 * 2 AND rsi > 55
        normalized["flag_beginner_pick"] = bool(
            _prev_high > 0 and _price > _prev_high
            and _vol_sma_10 > 0 and _volume > _vol_sma_10 * 2
            and _rsi > 55
        )

        return normalized
    except Exception as exc:
        logger.warning(f"Normalize failed: {exc}")
        return {
            "symbol": _s(raw.get("symbol") if isinstance(raw, dict) else None, "UNKNOWN"),
            "sector": "Others", "grade": "?", "score": 0, "price": 0,
            "chg_1d": 0, "chg_5d": 0, "chg_1m": 0, "chg_3m": 0,
            "rsi": 0, "adx": 0, "delivery_pct": 0, "vol_ratio": 0,
            "rs_alpha": 0, "rs_percentile": 0, "stage": "?",
            "active_signals": [], "trade_setup": {}, "score_breakdown": {},
            "score_top": [], "sparkline": [],
            "_normalize_error": str(exc),
        }


def _run_scan():
    """Background scan — runs the full NSE 500 analysis pipeline."""
    if not ANALYZER_AVAILABLE:
        _store["error"] = "Analyzer engine not loaded. Place analyzer.py in backend/ folder."
        return

    _store["scan_running"] = True
    _store["error"] = None
    _store["scan_progress"] = 0

    try:
        logger.info("🚀 Starting NSE 500 scan...")

        # Warm NSE session
        NSESession.get().warm()

        # Fetch market-wide data
        fetcher = NSEDataFetcher()
        symbols = fetcher.get_nifty500_list()

        # Cap universe to fit Render free-tier memory limit (512MB).
        # NIFTY 500 CSV is ordered by market cap, so the first N = large/mid-cap leaders.
        if _SCAN_UNIVERSE_LIMIT and len(symbols) > _SCAN_UNIVERSE_LIMIT:
            logger.info(f"🔻 Capping universe from {len(symbols)} → {_SCAN_UNIVERSE_LIMIT} (free-tier memory limit)")
            symbols = symbols[:_SCAN_UNIVERSE_LIMIT]

        _store["scan_total"] = len(symbols)

        pcr_data = fetcher.get_pcr_data()
        max_pain_data = MaxPainCalculator.fetch_nifty_max_pain()

        # Run pipeline
        pipeline = NSEAnalysisPipeline()
        pipeline.price_mgr.fetch_nifty()
        pipeline._pcr_data = pcr_data

        # max_workers reduced from 6 → 3 to cut peak memory usage
        output = pipeline.run(symbols, max_workers=3)

        if output:
            results, sorted_sectors, breadth_data, top_trades, fii_dii_data = output

            # Store results (normalized into uniform dict shape)
            _store["results"] = [_normalize_stock(r) for r in results]
            _store["top_trades"] = [_normalize_stock(t) for t in top_trades]
            _store["sectors"] = [
                {
                    "name": s[0], "strength": s[1], "avg_rs": s[2],
                    "count": s[3], "stage2_count": s[4],
                    "pct_above_200": s[5], "avg_adx": s[6]
                }
                for s in sorted_sectors
            ]
            _store["breadth"] = breadth_data
            _store["fii_dii"] = fii_dii_data
            _store["pcr"] = pcr_data
            _store["max_pain"] = max_pain_data

            # Build market pulse
            _store["market_pulse"] = {
                "breadth": breadth_data,
                "fii_dii": fii_dii_data,
                "pcr": pcr_data,
                "max_pain": max_pain_data,
                "total_stocks": len(results),
                "grade_distribution": _grade_dist(results),
                "advance_decline": _adv_dec(results),
            }

            _store["last_scan"] = datetime.now().isoformat()
            logger.info(f"✅ Scan complete: {len(results)} stocks analyzed")
            # Persist so data survives restarts / sleep cycles
            _save_cache()
        else:
            _store["error"] = "Scan returned no results"

    except Exception as e:
        logger.error(f"❌ Scan failed: {e}")
        _store["error"] = str(e)
    finally:
        _store["scan_running"] = False


def _grade_dist(results):
    dist = {}
    for r in results:
        g = r.get("grade", "?")
        dist[g] = dist.get(g, 0) + 1
    return dist


def _adv_dec(results):
    adv = sum(1 for r in results if r.get("chg_1d", 0) > 0)
    dec = sum(1 for r in results if r.get("chg_1d", 0) < 0)
    return {"advancing": adv, "declining": dec, "unchanged": len(results) - adv - dec}


# ─── DEMO DATA (used when analyzer is not loaded) ───
def _load_demo_data():
    """Generate realistic demo data for frontend development."""
    import random
    random.seed(42)

    sectors = ["IT", "Banking", "Pharma", "Energy", "FMCG", "Auto", "Metals",
               "Cement", "NBFC", "Telecom", "Chemicals", "Real Estate"]

    demo_stocks = [
        ("RELIANCE", "Reliance Industries", "Energy", 2456.50),
        ("TCS", "Tata Consultancy Services", "IT", 3890.25),
        ("HDFCBANK", "HDFC Bank", "Banking", 1645.80),
        ("INFY", "Infosys", "IT", 1520.35),
        ("ICICIBANK", "ICICI Bank", "Banking", 1078.90),
        ("HINDUNILVR", "Hindustan Unilever", "FMCG", 2350.60),
        ("ITC", "ITC Limited", "FMCG", 445.20),
        ("SBIN", "State Bank of India", "Banking", 628.75),
        ("BHARTIARTL", "Bharti Airtel", "Telecom", 1456.30),
        ("KOTAKBANK", "Kotak Mahindra Bank", "Banking", 1823.40),
        ("LT", "Larsen & Toubro", "Construction", 3245.60),
        ("AXISBANK", "Axis Bank", "Banking", 1156.80),
        ("ASIANPAINT", "Asian Paints", "Consumer Disc", 2890.45),
        ("MARUTI", "Maruti Suzuki", "Auto", 10567.30),
        ("TITAN", "Titan Company", "Consumer Disc", 3210.55),
        ("SUNPHARMA", "Sun Pharma", "Pharma", 1178.40),
        ("WIPRO", "Wipro", "IT", 467.25),
        ("ULTRACEMCO", "UltraTech Cement", "Cement", 9876.50),
        ("NESTLEIND", "Nestle India", "FMCG", 22345.80),
        ("TECHM", "Tech Mahindra", "IT", 1345.60),
        ("TATAMOTORS", "Tata Motors", "Auto", 678.90),
        ("TATASTEEL", "Tata Steel", "Metals", 134.55),
        ("JSWSTEEL", "JSW Steel", "Metals", 789.30),
        ("HINDALCO", "Hindalco Industries", "Metals", 534.20),
        ("BAJFINANCE", "Bajaj Finance", "NBFC", 6890.40),
        ("BAJAJFINSV", "Bajaj Finserv", "NBFC", 1567.80),
        ("NTPC", "NTPC Limited", "Energy", 356.45),
        ("POWERGRID", "Power Grid Corp", "Energy", 278.90),
        ("ONGC", "Oil & Natural Gas Corp", "Energy", 256.70),
        ("CIPLA", "Cipla", "Pharma", 1234.50),
        ("DRREDDY", "Dr Reddy's Labs", "Pharma", 5678.30),
        ("DIVISLAB", "Divi's Laboratories", "Pharma", 3890.20),
        ("COALINDIA", "Coal India", "Energy", 398.60),
        ("ADANIENT", "Adani Enterprises", "Infra", 2345.80),
        ("ADANIPORTS", "Adani Ports", "Infra", 1123.40),
        ("HCLTECH", "HCL Technologies", "IT", 1567.90),
        ("EICHERMOT", "Eicher Motors", "Auto", 4567.30),
        ("HEROMOTOCO", "Hero MotoCorp", "Auto", 4321.50),
        ("GRASIM", "Grasim Industries", "Cement", 2345.60),
        ("INDUSINDBK", "IndusInd Bank", "Banking", 1456.70),
        ("CHOLAFIN", "Cholamandalam Fin", "NBFC", 1234.50),
        ("MUTHOOTFIN", "Muthoot Finance", "NBFC", 1567.80),
        ("DLF", "DLF Limited", "Real Estate", 678.90),
        ("GODREJPROP", "Godrej Properties", "Real Estate", 2345.60),
        ("PIIND", "PI Industries", "Chemicals", 3456.70),
        ("DEEPAKNTR", "Deepak Nitrite", "Chemicals", 2134.50),
        ("SRF", "SRF Limited", "Chemicals", 2567.80),
        ("HAL", "Hindustan Aero", "Capital Goods", 4567.30),
        ("BEL", "Bharat Electronics", "Capital Goods", 234.50),
        ("ZOMATO", "Zomato", "Internet", 178.90),
    ]

    grades = ["A+", "A", "A", "B+", "B+", "B+", "B", "B", "B", "C", "C", "D"]
    expert_decisions = ["CONVICTION", "TRADE", "TRADE", "TRADE", "SKIP", "SKIP"]

    results = []
    for i, (sym, name, sector, base_price) in enumerate(demo_stocks):
        chg_1d = round(random.uniform(-3, 4), 2)
        chg_5d = round(random.uniform(-5, 8), 2)
        chg_1m = round(random.uniform(-10, 15), 2)
        chg_3m = round(random.uniform(-15, 25), 2)
        score = random.randint(25, 95)
        grade = "A+" if score >= 88 else "A" if score >= 67 else "B+" if score >= 54 else "B" if score >= 42 else "C" if score >= 28 else "D"
        rsi = round(random.uniform(35, 75), 1)
        adx = round(random.uniform(15, 45), 1)
        delivery = round(random.uniform(25, 75), 1)
        vol_ratio = round(random.uniform(0.5, 3.0), 2)
        rs_alpha = round(random.uniform(-10, 20), 2)
        rs_pctile = random.randint(10, 99)

        signals = []
        if score >= 70: signals.append("Supertrend-BUY")
        if delivery >= 55: signals.append(f"HighDelivery({delivery}%)")
        if vol_ratio >= 1.5: signals.append(f"VolSurge({vol_ratio}x)")
        if random.random() > 0.7: signals.append("NR7")
        if random.random() > 0.8: signals.append("GoldenCross")
        if random.random() > 0.85: signals.append("FlatBase")
        if random.random() > 0.9: signals.append("PocketPivot")

        oi_types = ["LongBuildup", "ShortCovering", "Neutral", "ShortBuildup", "LongUnwinding"]
        stages = ["Stage 2", "Stage 2", "Stage 1", "Stage 3", "Unknown"]

        entry_price = round(base_price * (1 + random.uniform(0, 0.02)), 2)
        sl_price = round(entry_price * (1 - random.uniform(0.03, 0.07)), 2)
        t1_price = round(entry_price * (1 + random.uniform(0.05, 0.15)), 2)
        t2_price = round(entry_price * (1 + random.uniform(0.10, 0.25)), 2)

        expert_yes = random.randint(4, 13)
        expert_dec = "CONVICTION" if expert_yes >= 10 else "TRADE" if expert_yes >= 7 else "SKIP"

        results.append({
            "symbol": sym,
            "name": name,
            "sector": sector,
            "price": round(base_price * (1 + chg_1d/100), 2),
            "chg_1d": chg_1d,
            "chg_5d": chg_5d,
            "chg_1m": chg_1m,
            "chg_3m": chg_3m,
            "score": score,
            "grade": grade,
            "rsi": rsi,
            "adx": adx,
            "ema_21": round(base_price * 0.98, 2),
            "ema_50": round(base_price * 0.95, 2),
            "ema_200": round(base_price * 0.88, 2),
            "delivery_pct": delivery,
            "vol_ratio": vol_ratio,
            "rs_alpha": rs_alpha,
            "rs_percentile": rs_pctile,
            "active_signals": signals,
            "oi_data": {"buildup_type": random.choice(oi_types), "oi_change_pct": round(random.uniform(-5, 8), 2)},
            "stage": random.choice(stages),
            "is_stage2": random.random() > 0.6,
            "supertrend_dir": 1 if score >= 50 else -1,
            "breakout": random.random() > 0.85,
            "vcp_score": random.randint(20, 90),
            "is_fno": sym in FNO_STOCKS if ANALYZER_AVAILABLE else random.random() > 0.3,
            "fund_grade": random.choice(["Strong", "Moderate", "Weak"]),
            "confidence_pct": min(95, max(20, score + random.randint(-10, 10))),
            "trade_setup": {
                "entry": entry_price,
                "stop_loss": sl_price,
                "target1": t1_price,
                "target2": t2_price,
                "rr_ratio": round((t1_price - entry_price) / max(entry_price - sl_price, 0.01), 2),
                "setup_type": random.choice(["Breakout", "Pullback", "VCP", "FlatBase", "NR7"]),
                "risk_pct": round((entry_price - sl_price) / entry_price * 100, 2),
            },
            "expert_checks": {
                "a1_nifty_above_dma": random.random() > 0.3,
                "a2_breadth_supportive": random.random() > 0.4,
                "b1_sector_strong": random.random() > 0.4,
                "b2_sector_peers_breaking": random.random() > 0.5,
                "c1_base_consolidation": random.random() > 0.4,
                "c2_price_structure_ok": random.random() > 0.3,
                "d1_breakout_confirmed": random.random() > 0.5,
                "d2_candle_quality_ok": random.random() > 0.4,
                "e1_volume_surge": random.random() > 0.5,
                "e2_volume_contraction": random.random() > 0.4,
                "f1_indicators_aligned": random.random() > 0.5,
                "g1_stoploss_defined": random.random() > 0.3,
                "g2_rr_minimum": random.random() > 0.4,
            },
            "expert_yes": expert_yes,
            "expert_decision": expert_dec,
            "promoter_data": {
                "promoter_holding": round(random.uniform(30, 75), 2),
                "promoter_chg_qoq": round(random.uniform(-2, 3), 2),
                "promoter_buying": random.random() > 0.7,
                "promoter_selling": random.random() > 0.85,
                "pledge_pct": round(random.uniform(0, 15), 2),
            },
            "bulk_deal": {
                "bulk_buy": random.random() > 0.9,
                "block_buy": random.random() > 0.92,
                "bulk_sell": random.random() > 0.95,
            },
            "earnings_info": {"has_upcoming": random.random() > 0.85},
            "pct_from_high": round(random.uniform(-25, 0), 2),
            "bb_width": round(random.uniform(3, 20), 2),
            "candle_patterns": random.sample(["Hammer", "Engulfing", "MorningStar", "Doji"], k=random.randint(0, 2)),
            "score_breakdown": {
                "delivery": random.randint(0, 12),
                "fii_dii": random.randint(-5, 6),
                "bulk_deal": random.randint(-5, 12),
                "promoter": random.randint(-10, 10),
                "vix": random.randint(-5, 8),
                "oi_buildup": random.randint(-5, 10),
                "pcr": random.randint(0, 6),
                "compression": random.randint(0, 14),
                "vol_dryup": random.randint(0, 8),
                "base_position": random.randint(0, 8),
                "supertrend": random.randint(0, 10),
                "ema_alignment": random.randint(0, 6),
                "rsi": random.randint(0, 9),
                "adx": random.randint(0, 8),
                "weekly_trend": random.randint(0, 6),
                "golden_cross": random.randint(-8, 8),
                "freshness": random.randint(-15, 0),
            },
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # Top trades = top 10 by confidence
    top_trades = sorted(results[:20], key=lambda x: x["confidence_pct"], reverse=True)[:10]

    # Sector data
    sector_data = []
    for sec in sectors:
        sec_stocks = [r for r in results if r["sector"] == sec]
        if sec_stocks:
            sector_data.append({
                "name": sec,
                "strength": round(random.uniform(40, 85), 1),
                "avg_rs": round(sum(r["rs_alpha"] for r in sec_stocks) / len(sec_stocks), 2),
                "count": len(sec_stocks),
                "stage2_count": sum(1 for r in sec_stocks if r["is_stage2"]),
                "pct_above_200": round(sum(1 for r in sec_stocks if r["price"] > r["ema_200"]) / len(sec_stocks) * 100, 1),
                "avg_adx": round(sum(r["adx"] for r in sec_stocks) / len(sec_stocks), 1),
            })
    sector_data.sort(key=lambda x: x["strength"], reverse=True)

    # Store demo data
    _store["results"] = results
    _store["top_trades"] = top_trades
    _store["sectors"] = sector_data
    _store["breadth"] = {"pct": 62.4, "status": "STRONG", "above_200": 312, "total": 500}
    _store["fii_dii"] = {
        "fii_net": 2345.6, "dii_net": -1234.5, "fii_5d": 8567.8,
        "sentiment": "Bullish", "fii_buy": 15678.9, "fii_sell": 13333.3,
        "dii_buy": 12456.7, "dii_sell": 13691.2
    }
    _store["pcr"] = {
        "nifty_pcr": 1.18, "weekly_pcr": 1.24, "sentiment": "Bullish",
        "weekly_sentiment": "Bullish", "total_pe_oi": 45678900,
        "total_ce_oi": 38710000, "weekly_expiry": "10-Apr-2026",
        "monthly_expiry": "30-Apr-2026", "fetched": True
    }
    _store["max_pain"] = {
        "max_pain": 23200, "cmp": 23123.65, "distance_pct": -0.33,
        "sentiment": "Price near Max Pain", "fetched": True
    }
    _store["market_pulse"] = {
        "breadth": _store["breadth"],
        "fii_dii": _store["fii_dii"],
        "pcr": _store["pcr"],
        "max_pain": _store["max_pain"],
        "total_stocks": len(results),
        "grade_distribution": _grade_dist(results),
        "advance_decline": _adv_dec(results),
        "indices": {
            "NIFTY 50": {"value": 23123.65, "change": 155.40, "pct": 0.68},
            "NIFTY 100": {"value": 23730.25, "change": 150.80, "pct": 0.64},
            "NIFTY 200": {"value": 12958.15, "change": 71.75, "pct": 0.56},
            "NIFTY 500": {"value": 21296.45, "change": 102.40, "pct": 0.48},
            "NIFTY BANK": {"value": 48456.30, "change": -123.45, "pct": -0.25},
            "NIFTY IT": {"value": 31403.35, "change": 765.80, "pct": 2.50},
        },
        "india_vix": {"value": 14.23, "change": -0.45, "pct": -3.07},
    }
    _store["last_scan"] = datetime.now().isoformat()
    logger.info("📊 Demo data loaded successfully")


# Startup: try cached scan first, fall back to demo data
if _load_cache():
    logger.info("✅ Loaded previous scan from cache — skipping demo data")
else:
    logger.info("ℹ️ No cache found — loading demo data")
    _load_demo_data()


# ─── API ENDPOINTS ───

@app.get("/api/status")
def get_status():
    return {
        "last_scan": _store["last_scan"],
        "scan_running": _store["scan_running"],
        "scan_progress": _store["scan_progress"],
        "scan_total": _store["scan_total"],
        "total_stocks": len(_store["results"]),
        "error": _store["error"],
        "analyzer_available": ANALYZER_AVAILABLE,
    }


@app.post("/api/scan")
def trigger_scan():
    if _store["scan_running"]:
        return {"status": "already_running"}
    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()
    return {"status": "started"}


@app.get("/api/market-pulse")
def get_market_pulse():
    try:
        mp = dict(_store.get("market_pulse") or {})
        # Always recompute grade_distribution and advance_decline from current results
        # in case the analyzer didn't populate market_pulse
        results = _store.get("results") or []
        norm = []
        for r in results:
            norm.append(r if (isinstance(r, dict) and "grade" in r) else _normalize_stock(r))

        if norm:
            mp.setdefault("total_stocks", len(norm))
            mp["grade_distribution"] = _grade_dist(norm)
            mp["advance_decline"] = _adv_dec(norm)
            mp.setdefault("breadth", _store.get("breadth") or {})
            mp.setdefault("fii_dii", _store.get("fii_dii") or {})
            mp.setdefault("pcr", _store.get("pcr") or {})
            mp.setdefault("max_pain", _store.get("max_pain") or {})
        return mp
    except Exception as e:
        logger.exception("Market-pulse endpoint failed")
        return {"error": f"{type(e).__name__}: {e}"}


@app.get("/api/all")
def get_all_stocks():
    """Return ALL normalized stocks at once. Frontend filters/sorts client-side
    to match the original analyzer's HTML report behavior."""
    try:
        results = []
        for r in _store["results"]:
            rec = r if (isinstance(r, dict) and "grade" in r and "score" in r) else _normalize_stock(r)
            results.append(rec)

        # Compute scanner counts (used by sidebar badges)
        counts = {
            "all": len(results),
            "aplus": sum(1 for r in results if r.get("flag_aplus")),
            "expert": sum(1 for r in results if r.get("flag_expert_pick")),
            "trade": sum(1 for r in results if r.get("flag_strong_grade") and not r.get("pledge_danger")),
            "breakouts": sum(1 for r in results if r.get("flag_breakout")),
            "volsurge": sum(1 for r in results if r.get("flag_vol_surge")),
            "accumulation": sum(1 for r in results if r.get("flag_accumulation")),
            "ema": sum(1 for r in results if r.get("flag_ema_scanner")),
            "vcp": sum(1 for r in results if r.get("flag_vcp")),
            "rs": sum(1 for r in results if r.get("flag_rs_elite")),
            "stage2": sum(1 for r in results if r.get("flag_stage2")),
            "price_action": sum(1 for r in results if r.get("flag_price_action")),
            "fundamentals": sum(1 for r in results if r.get("flag_fund_strong")),
            "value_screen": sum(1 for r in results if r.get("flag_value_screen")),
            "quality_screen": sum(1 for r in results if r.get("flag_quality_screen")),
            "low_reversal": sum(1 for r in results if r.get("flag_low_reversal")),
            "delivery_spike": sum(1 for r in results if r.get("flag_delivery_spike")),
            "promoter_buy": sum(1 for r in results if r.get("flag_promoter_buying")),
            "bb_squeeze": sum(1 for r in results if r.get("flag_bb_squeeze")),
            "ipo_base": sum(1 for r in results if r.get("flag_ipo_base")),
            "dryup_pattern": sum(1 for r in results if r.get("flag_dryup_pattern")),
            "near_52w_high": sum(1 for r in results if r.get("flag_52w_breakout_zone")),
            "avwap_breakout": sum(1 for r in results if r.get("flag_avwap_breakout")),
            "vol_2x_bull": sum(1 for r in results if r.get("flag_vol_2x_bull")),
            "vol_3x_breakout": sum(1 for r in results if r.get("flag_vol_3x_breakout")),
            "bull_breakout_vol": sum(1 for r in results if r.get("flag_bull_breakout_vol")),
            "rsi50_cross": sum(1 for r in results if r.get("flag_rsi50_cross")),
            "ema200_cross": sum(1 for r in results if r.get("flag_ema200_cross")),
            "sma20_breakout": sum(1 for r in results if r.get("flag_sma20_breakout")),
            "btst_bull": sum(1 for r in results if r.get("flag_btst_bull")),
            "strong_momentum": sum(1 for r in results if r.get("flag_strong_momentum")),
            "gap_up_vol": sum(1 for r in results if r.get("flag_gap_up_vol")),
            "delivery_strong": sum(1 for r in results if r.get("flag_delivery_strong")),
            "beginner_pick": sum(1 for r in results if r.get("flag_beginner_pick")),
            "sectors": len(_store.get("sectors") or []),
        }

        return {
            "total": len(results),
            "stocks": results,
            "counts": counts,
            "sectors": _store.get("sectors") or [],
            "market_pulse": _store.get("market_pulse") or {},
            "last_scan": _store.get("last_scan"),
        }
    except Exception as e:
        logger.exception("All-stocks endpoint failed")
        return {"total": 0, "stocks": [], "counts": {}, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/debug/first")
def debug_first_stock():
    """Returns the first stock record + its type info. Use this to see what your analyzer actually produced."""
    raw = _store["results"][0] if _store["results"] else None
    return {
        "total_stocks": len(_store["results"]),
        "type": type(raw).__name__ if raw is not None else None,
        "is_dict": isinstance(raw, dict),
        "sample_keys": (list(raw.keys()) if isinstance(raw, dict) else
                        list(raw.__dict__.keys()) if hasattr(raw, "__dict__") else None),
        "sample_record": raw if isinstance(raw, dict) else
                         (raw.__dict__ if hasattr(raw, "__dict__") else str(raw)),
    }


@app.get("/api/debug/raw-sample")
def debug_raw_sample(n: int = 3):
    """Returns first N normalized stocks (what the frontend actually sees)."""
    return {"count": len(_store["results"]), "sample": _store["results"][:n]}


@app.get("/api/screener")
def get_screener(
    grade: Optional[str] = Query(None, description="Filter by grade: A+, A, B+, B, C, D"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    min_score: Optional[int] = Query(None, description="Minimum score"),
    signal: Optional[str] = Query(None, description="Filter by active signal"),
    sort_by: Optional[str] = Query("score", description="Sort field"),
    sort_dir: Optional[str] = Query("desc", description="Sort direction: asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=500),
):
    try:
        # If results aren't normalized (e.g. old scan before patch), normalize them now
        raw_results = _store["results"]
        results = []
        for r in raw_results:
            if isinstance(r, dict) and "grade" in r and "score" in r and "symbol" in r:
                results.append(r)
            else:
                results.append(_normalize_stock(r))

        # Filters — all use .get() so missing fields never crash
        if grade:
            results = [r for r in results if r.get("grade") == grade]
        if sector:
            results = [r for r in results if r.get("sector", "").lower() == sector.lower()]
        if min_score is not None:
            results = [r for r in results if (r.get("score") or 0) >= min_score]
        if signal:
            results = [r for r in results if any(signal.lower() in str(s).lower()
                                                 for s in (r.get("active_signals") or []))]

        # Sort
        reverse = sort_dir == "desc"
        if sort_by in ["score", "price", "chg_1d", "chg_5d", "chg_1m", "chg_3m",
                        "delivery_pct", "vol_ratio", "rs_alpha", "rs_percentile",
                        "rsi", "adx", "confidence_pct", "vcp_score"]:
            results = sorted(results, key=lambda x: x.get(sort_by) or 0, reverse=reverse)
        elif sort_by == "symbol":
            results = sorted(results, key=lambda x: x.get("symbol", ""), reverse=reverse)
        elif sort_by == "grade":
            grade_order = {"A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}
            results = sorted(results, key=lambda x: grade_order.get(x.get("grade", ""), 0), reverse=reverse)

        # Pagination
        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": results[start:end],
        }
    except Exception as e:
        logger.exception("Screener endpoint failed")
        return JSONResponse(
            status_code=200,
            content={"total": 0, "page": 1, "page_size": 50, "results": [],
                     "error": f"{type(e).__name__}: {e}"}
        )


@app.get("/api/stock/{symbol}")
def get_stock_detail(symbol: str):
    symbol = symbol.upper()
    for r in _store["results"]:
        try:
            rec = r if (isinstance(r, dict) and "symbol" in r) else _normalize_stock(r)
            if str(rec.get("symbol", "")).upper() == symbol:
                return rec
        except Exception:
            continue
    raise HTTPException(status_code=404, detail=f"Stock {symbol} not found in latest scan")


@app.get("/api/top-trades")
def get_top_trades(capital: float = Query(500000, description="Trading capital in INR")):
    try:
        raw_trades = _store["top_trades"] or []
        # If we don't have explicit top_trades, fall back to top-graded results
        if not raw_trades:
            normalized = []
            for r in _store["results"]:
                rec = r if (isinstance(r, dict) and "symbol" in r) else _normalize_stock(r)
                if rec.get("grade") in ("A+", "A", "B+"):
                    normalized.append(rec)
            normalized.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
            raw_trades = normalized[:20]
        else:
            raw_trades = [t if (isinstance(t, dict) and "symbol" in t) else _normalize_stock(t) for t in raw_trades]

        risk_pct = 2.0
        enriched = []
        for t in raw_trades:
            ts = t.get("trade_setup", {}) or {}
            entry = float(ts.get("entry") or 0)
            sl = float(ts.get("stop_loss") or 0)
            risk_per_share = entry - sl if entry and sl and entry > sl else 0
            risk_amount = capital * risk_pct / 100
            qty = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
            position_value = qty * entry if entry else 0

            enriched.append({
                **t,
                "position_qty": qty,
                "position_value": round(position_value, 2),
                "risk_amount": round(risk_amount, 2),
            })

        return {"capital": capital, "risk_pct": risk_pct, "trades": enriched}
    except Exception as e:
        logger.exception("Top-trades endpoint failed")
        return {"capital": capital, "risk_pct": 2.0, "trades": [],
                "error": f"{type(e).__name__}: {e}"}


@app.get("/api/sectors")
def get_sectors():
    try:
        sectors = _store.get("sectors") or []
        # If sectors weren't computed by analyzer, derive from normalized results
        if not sectors and _store.get("results"):
            buckets = {}
            for r in _store["results"]:
                rec = r if (isinstance(r, dict) and "symbol" in r) else _normalize_stock(r)
                sec = rec.get("sector") or "Unknown"
                b = buckets.setdefault(sec, {"name": sec, "count": 0, "scores": [], "rs": [],
                                              "stage2": 0, "above_200": 0, "adx": []})
                b["count"] += 1
                b["scores"].append(rec.get("score") or 0)
                b["rs"].append(rec.get("rs_alpha") or 0)
                if str(rec.get("stage", "")).lower().startswith("stage 2"):
                    b["stage2"] += 1
                if (rec.get("price") or 0) > (rec.get("ema_200") or 0) > 0:
                    b["above_200"] += 1
                b["adx"].append(rec.get("adx") or 0)

            sectors = []
            for name, b in buckets.items():
                cnt = max(b["count"], 1)
                avg_score = sum(b["scores"]) / cnt
                avg_rs = sum(b["rs"]) / cnt
                avg_adx = sum(b["adx"]) / cnt
                sectors.append({
                    "name": name,
                    "strength": round(avg_score, 1),
                    "avg_rs": round(avg_rs, 2),
                    "count": b["count"],
                    "stage2_count": b["stage2"],
                    "pct_above_200": round(b["above_200"] / cnt * 100, 1),
                    "avg_adx": round(avg_adx, 1),
                })
            sectors.sort(key=lambda s: s["strength"], reverse=True)
        return {"sectors": sectors}
    except Exception as e:
        logger.exception("Sectors endpoint failed")
        return {"sectors": [], "error": f"{type(e).__name__}: {e}"}


@app.get("/api/search")
def search_stocks(q: str = Query(..., min_length=1)):
    try:
        q = q.upper()
        matches = []
        for r in _store["results"]:
            rec = r if (isinstance(r, dict) and "symbol" in r) else _normalize_stock(r)
            sym = str(rec.get("symbol", "")).upper()
            name = str(rec.get("name", "")).upper()
            if q in sym or q in name:
                matches.append({
                    "symbol": rec.get("symbol", ""),
                    "name": rec.get("name", rec.get("symbol", "")),
                    "sector": rec.get("sector", ""),
                })
            if len(matches) >= 10:
                break
        return {"results": matches}
    except Exception as e:
        logger.exception("Search endpoint failed")
        return {"results": [], "error": f"{type(e).__name__}: {e}"}



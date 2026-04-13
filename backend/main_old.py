"""
Trade Stag — FastAPI Backend
Wraps the NSE 500 Swing Analyzer v7.1 engine as REST API endpoints.

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
        _store["scan_total"] = len(symbols)

        pcr_data = fetcher.get_pcr_data()
        max_pain_data = MaxPainCalculator.fetch_nifty_max_pain()

        # Run pipeline
        pipeline = NSEAnalysisPipeline()
        pipeline.price_mgr.fetch_nifty()
        pipeline._pcr_data = pcr_data

        output = pipeline.run(symbols, max_workers=6)

        if output:
            results, sorted_sectors, breadth_data, top_trades, fii_dii_data = output

            # Store results
            _store["results"] = results
            _store["top_trades"] = top_trades
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


# Load demo data on startup
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
    return _store["market_pulse"]


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
    results = _store["results"]

    # Filters
    if grade:
        results = [r for r in results if r["grade"] == grade]
    if sector:
        results = [r for r in results if r.get("sector", "").lower() == sector.lower()]
    if min_score:
        results = [r for r in results if r["score"] >= min_score]
    if signal:
        results = [r for r in results if any(signal.lower() in s.lower() for s in r.get("active_signals", []))]

    # Sort
    reverse = sort_dir == "desc"
    if sort_by in ["score", "price", "chg_1d", "chg_5d", "chg_1m", "chg_3m",
                    "delivery_pct", "vol_ratio", "rs_alpha", "rs_percentile",
                    "rsi", "adx", "confidence_pct", "vcp_score"]:
        results = sorted(results, key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
    elif sort_by == "symbol":
        results = sorted(results, key=lambda x: x.get("symbol", ""), reverse=reverse)
    elif sort_by == "grade":
        grade_order = {"A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}
        results = sorted(results, key=lambda x: grade_order.get(x["grade"], 0), reverse=reverse)

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


@app.get("/api/stock/{symbol}")
def get_stock_detail(symbol: str):
    symbol = symbol.upper()
    for r in _store["results"]:
        if r["symbol"] == symbol:
            return r
    raise HTTPException(status_code=404, detail=f"Stock {symbol} not found in latest scan")


@app.get("/api/top-trades")
def get_top_trades(capital: float = Query(500000, description="Trading capital in INR")):
    trades = _store["top_trades"]
    risk_pct = 2.0  # 2% risk per trade

    enriched = []
    for t in trades:
        ts = t.get("trade_setup", {})
        entry = ts.get("entry", 0)
        sl = ts.get("stop_loss", 0)
        risk_per_share = entry - sl if entry and sl else 0
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


@app.get("/api/sectors")
def get_sectors():
    return {"sectors": _store["sectors"]}


@app.get("/api/search")
def search_stocks(q: str = Query(..., min_length=1)):
    q = q.upper()
    matches = [
        {"symbol": r["symbol"], "name": r.get("name", r["symbol"]), "sector": r.get("sector", "")}
        for r in _store["results"]
        if q in r["symbol"] or q in r.get("name", "").upper()
    ][:10]
    return {"results": matches}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

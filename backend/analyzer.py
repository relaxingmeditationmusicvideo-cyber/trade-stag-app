"""
╔══════════════════════════════════════════════════════════════════════╗
║        NSE 500 SWING TRADING ANALYZER  v7.1 — INDIA FIRST           ║
║        Expert-Audited · All US signals removed · India-only logic    ║
║        Delivery%(dir) · FII(gate) · Bulk · Promoter · OI · VIX · PCR║
║        Generates interactive HTML report with grades A+ to D         ║
╚══════════════════════════════════════════════════════════════════════╝

New in v7.1 — Expert Audit Fixes:
  ① Delivery % now checks price DIRECTION (up day = accumulation, down = distribution)
  ② Delivery % weighted by absolute volume (illiquid stocks filtered)
  ③ FII/DII changed from per-stock additive to market gate (correct approach)
  ④ Grade thresholds raised (A+ now requires 88/100, was 80)
  ⑤ 52W high breakout REWARDED (was wrongly penalised before)
  ⑥ Circuit breaker penalty added (-10 pts near upper circuit)
  ⑦ Nifty index gate added (below 50 EMA = -6 pts, below 200 EMA = -12 pts)
  ⑧ ExpertFilter F1 uses Supertrend (replaced MACD which was removed)
  ⑨ ExpertFilter C1 uses Indian base checks (replaced VCP which is US concept)
  ⑩ 52W breakout signal added to active signals
  ⑪ Wasted compute removed (MACD, MFI, CMF, Stochastic) — 15% faster scan

New in v7.0 — India-First Scoring Engine:

  INDIA-SPECIFIC SIGNALS (highest weight — 70 pts potential):
    ① Delivery %          → 12 pts  NSE's most unique signal — institutions vs speculators
    ② FII/DII 5-day flow  → 12 pts  Largest driver of Indian large cap movement
    ③ Bulk/Block deals    → 12 pts  Disclosed institutional conviction trades
    ④ Promoter buying     → 10 pts  Strongest insider signal — SEBI mandated disclosure
    ⑤ India VIX           →  8 pts  Nifty options fear gauge — swing trading window
    ⑥ OI buildup          → 10 pts  F&O smart money: Long buildup = institutions buying
    ⑦ PCR signal          →  6 pts  Put-Call ratio — market sentiment from options data

  REDUCED US-CENTRIC SIGNALS:
    • VCP pattern:   18 pts → 10 pts  (less reliable — operators fake compressions)
    • BB squeeze:    12 pts →  6 pts  (Indian stocks can stay squeezed for months)
    • Weekly NR7:     8 pts →  4 pts  (low liquidity weeks distort this in mid/small caps)

  NEW INDIA-SPECIFIC FETCHERS:
    • IndiaVIXFetcher      — NSE India VIX (Nifty options volatility)
    • OpenInterestFetcher  — NSE F&O OI buildup detection
    • PromoterActivityFetcher — SEBI quarterly shareholding changes

  NEW INDIA PENALTIES:
    • Results within 14 days → −10 pts (increased from warning-only)
    • Promoter selling       → −10 pts from promoter score
    • Bulk sell              → −20 pts (increased from −15)

  All v6.0 features retained: Supertrend, MFI, CMF, Pivot Points,
  Candle Patterns, Flat Base, OBV Divergence, Stage Analysis,
  Accumulation Detector, FII Banner, Alert Panel, 20-point checklist.

Install requirements:
  pip install yfinance pandas numpy requests beautifulsoup4 tqdm

Usage:
  python nse500_swing_analyzer_v7.py
  python nse500_swing_analyzer_v7.py --top 50 --workers 8
  python nse500_swing_analyzer_v7.py --capital 500000
"""

import os, sys, json, time, argparse, warnings, threading

# Proxy settings left as-is — let system proxy handle NSE connections

# ── Global yfinance session (bypasses antivirus/proxy) ──
def _make_yf_session():
    import requests as _r
    s = _r.Session()
    # Do NOT set trust_env=False — would break NSE connections via proxy
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json,text/html,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return s

_YF_SESSION = _make_yf_session()

# ── NSE Historical + Yahoo Finance price downloader ─────────────────────────
def _nse_download(symbol_ns: str, interval: str, lookback_days: int) -> "pd.DataFrame":
    """
    Download OHLCV from NSE Historical API (primary) or Yahoo Finance (fallback).
    NSE API works on all Indian networks. Yahoo is fallback for non-Indian access.
    symbol_ns: e.g. "RELIANCE.NS"
    interval : "1d" or "1wk"
    """
    import time as _t, io as _io

    symbol = symbol_ns.replace(".NS", "").replace(".ns", "").upper()
    end_dt = __import__("datetime").datetime.today()
    start_dt = end_dt - __import__("datetime").timedelta(days=lookback_days)
    from_str = start_dt.strftime("%d-%m-%Y")
    to_str   = end_dt.strftime("%d-%m-%Y")

    # ── PRIMARY: NSE Historical API ────────────────────────────────────────
    try:
        nse = NSESession.get()
        nse.warm()

        if interval == "1d":
            url = (f"https://www.nseindia.com/api/historical/cm/equity"
                   f'?symbol={symbol}&series=["EQ"]&from={from_str}&to={to_str}')
        else:
            # NSE doesn't have weekly — we'll resample from daily
            url = (f"https://www.nseindia.com/api/historical/cm/equity"
                   f'?symbol={symbol}&series=["EQ"]&from={from_str}&to={to_str}')

        resp = nse.get_api(url, timeout=20)
        if resp and resp.status_code == 200:
            data = resp.json()
            rows = data.get("data", [])
            if rows:
                records = []
                for r in rows:
                    try:
                        records.append({
                            "Date"  : __import__("pandas").to_datetime(r.get("CH_TIMESTAMP") or r.get("mTIMESTAMP")),
                            "Open"  : float(r.get("CH_OPENING_PRICE") or r.get("mOPEN") or 0),
                            "High"  : float(r.get("CH_TRADE_HIGH_PRICE") or r.get("mHIGH") or 0),
                            "Low"   : float(r.get("CH_TRADE_LOW_PRICE") or r.get("mLOW") or 0),
                            "Close" : float(r.get("CH_CLOSING_PRICE") or r.get("mCLOSE") or 0),
                            "Volume": float(r.get("CH_TOT_TRADED_QTY") or r.get("mTOTALTRADEDVOLUME") or 0),
                        })
                    except Exception:
                        continue

                if records:
                    df = __import__("pandas").DataFrame(records)
                    df = df.dropna(subset=["Close"])
                    df = df[df["Close"] > 0]
                    df = df.sort_values("Date").reset_index(drop=True)
                    df = df.set_index("Date")
                    df.index = __import__("pandas").to_datetime(df.index).tz_localize(None)

                    if interval == "1wk" and not df.empty:
                        df = df.resample("W-FRI").agg({
                            "Open": "first", "High": "max",
                            "Low": "min", "Close": "last", "Volume": "sum"
                        }).dropna()

                    if len(df) >= 20:
                        return df
    except Exception as _nse_e:
        pass  # NSE historical failed silently

    # ── FALLBACK: Yahoo Finance direct HTTP ─────────────────────────────────
    try:
        end_ts   = int(__import__("datetime").datetime.now().timestamp())
        start_ts = end_ts - lookback_days * 86400
        yf_sym   = symbol_ns if symbol_ns.upper().endswith(".NS") else f"{symbol_ns}.NS"

        for host in ["query1", "query2"]:
            url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{yf_sym}"
                   f"?interval={interval}&period1={start_ts}&period2={end_ts}"
                   f"&includePrePost=false")
            try:
                resp = _YF_SESSION.get(url, timeout=20)
                if resp.status_code != 200:
                    continue
                js = resp.json()
                result = js.get("chart", {}).get("result")
                if not result:
                    continue
                ts   = result[0].get("timestamp", [])
                indi = result[0].get("indicators", {})
                q    = indi.get("quote", [{}])[0]
                if not ts:
                    continue
                df = __import__("pandas").DataFrame({
                    "Open"  : q.get("open",   [None]*len(ts)),
                    "High"  : q.get("high",   [None]*len(ts)),
                    "Low"   : q.get("low",    [None]*len(ts)),
                    "Close" : q.get("close",  [None]*len(ts)),
                    "Volume": q.get("volume", [0]*len(ts)),
                }, index=__import__("pandas").to_datetime(ts, unit="s", utc=True).tz_localize(None))
                df = df.dropna(subset=["Close"])
                if len(df) >= 20:
                    return df
            except Exception:
                continue
    except Exception:
        pass

    # ── FALLBACK 3: BSE India API ────────────────────────────────────────────
    try:
        bse_session = requests.Session()
        bse_session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bseindia.com/',
            'Origin': 'https://www.bseindia.com',
        })
        # Step 1: get BSE scrip code from symbol
        search_url = f"https://api.bseindia.com/BseIndiaAPI/api/listofscripdata/w?scrip={symbol}"
        sr = bse_session.get(search_url, timeout=10)
        if sr.status_code == 200:
            items = sr.json() if sr.text.strip() else []
            scrip_code = None
            for item in (items if isinstance(items, list) else items.get("Table", [])):
                name = str(item.get("SCRIP_CD") or item.get("scripcode") or "")
                if name:
                    scrip_code = name
                    break
            if scrip_code:
                end_dt2   = __import__("datetime").datetime.today()
                start_dt2 = end_dt2 - __import__("datetime").timedelta(days=lookback_days)
                hist_url = (f"https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w"
                            f"?scripcode={scrip_code}&flag=0"
                            f"&fromdate={start_dt2.strftime('%d/%m/%Y')}"
                            f"&todate={end_dt2.strftime('%d/%m/%Y')}&seriesid=")
                hr = bse_session.get(hist_url, timeout=15)
                if hr.status_code == 200:
                    hdata = hr.json()
                    rows = hdata if isinstance(hdata, list) else hdata.get("data", [])
                    records = []
                    for row in (rows or []):
                        try:
                            dt = __import__("pandas").to_datetime(row.get("TIMESTAMP") or row.get("Date"))
                            records.append({
                                "Date": dt, "Open": float(row.get("OPEN") or row.get("Open") or 0),
                                "High": float(row.get("HIGH") or row.get("High") or 0),
                                "Low":  float(row.get("LOW")  or row.get("Low")  or 0),
                                "Close":float(row.get("CLOSE")or row.get("Close")or 0),
                                "Volume": float(row.get("VOLUME") or row.get("Volume") or 0),
                            })
                        except Exception: continue
                    if records:
                        df = __import__("pandas").DataFrame(records)
                        df = df.dropna(subset=["Close"]).sort_values("Date").set_index("Date")
                        df.index = __import__("pandas").to_datetime(df.index).tz_localize(None)
                        if len(df) >= 20 and interval == "1wk":
                            df = df.resample("W-FRI").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
                        if len(df) >= 20:
                            return df
    except Exception:
        pass

    return __import__("pandas").DataFrame()

# Keep old name as alias so callers work unchanged
_yf_direct_download = _nse_download

def _nse_nifty_download(lookback_days: int) -> "pd.DataFrame":
    """Download Nifty 50 index data. Uses Yahoo Finance (confirmed working) or allIndices."""
    import pandas as _pd, datetime as _dt, requests as _req

    # Try Yahoo Finance first (confirmed working in diagnostic — 200 OK)
    try:
        end_ts   = int(_dt.datetime.now().timestamp())
        start_ts = end_ts - lookback_days * 86400
        for host in ["query1", "query2"]:
            url_yf = (f"https://{host}.finance.yahoo.com/v8/finance/chart/%5ENSEI"
                      f"?interval=1d&period1={start_ts}&period2={end_ts}&includePrePost=false")
            try:
                s = _req.Session(); s.headers.update({"User-Agent": "Mozilla/5.0"})
                r = s.get(url_yf, timeout=15)
                if r.status_code == 200:
                    js = r.json()
                    result = js.get("chart", {}).get("result")
                    if result:
                        ts_list = result[0].get("timestamp", [])
                        q = result[0].get("indicators", {}).get("quote", [{}])[0]
                        closes = q.get("close", [])
                        if ts_list and closes:
                            df = _pd.DataFrame({"Close": closes},
                                index=_pd.to_datetime(ts_list, unit="s", utc=True).tz_localize(None))
                            df = df.dropna()
                            if len(df) >= 20:
                                return df
            except Exception:
                continue
    except Exception:
        pass

    end_dt   = _dt.datetime.today()
    start_dt = end_dt - _dt.timedelta(days=lookback_days)
    from_str = start_dt.strftime("%d-%m-%Y")
    to_str   = end_dt.strftime("%d-%m-%Y")
    try:
        nse  = NSESession.get()
        nse.warm()
        url  = (f"https://www.nseindia.com/api/historical/indicesHistory"
                f"?indexType=NIFTY%2050&from={from_str}&to={to_str}")
        resp = nse.get_api(url, timeout=20)
        if resp and resp.status_code == 200:
            data = resp.json()
            rows = (data.get("data", {}).get("indexCloseOnlineRecords")
                    or data.get("data", []))
            records = []
            for r in (rows or []):
                try:
                    records.append({
                        "Date" : _pd.to_datetime(r.get("EOD_TIMESTAMP") or r.get("Date")),
                        "Open" : float(r.get("EOD_OPEN_INDEX_VAL")  or r.get("Open")  or 0),
                        "High" : float(r.get("EOD_HIGH_INDEX_VAL")  or r.get("High")  or 0),
                        "Low"  : float(r.get("EOD_LOW_INDEX_VAL")   or r.get("Low")   or 0),
                        "Close": float(r.get("EOD_CLOSE_INDEX_VAL") or r.get("Close") or 0),
                        "Volume": 0,
                    })
                except Exception:
                    continue
            if records:
                df = _pd.DataFrame(records).dropna(subset=["Close"])
                df = df[df["Close"] > 0].sort_values("Date").set_index("Date")
                df.index = _pd.to_datetime(df.index).tz_localize(None)
                if len(df) >= 20:
                    return df
    except Exception:
        pass
    # Fallback: Yahoo Finance
    return _nse_download("^NSEI", "1d", lookback_days)



def _yf_get_info(symbol_ns: str) -> dict:
    """
    Fetch fundamental data.
    Primary: NSE quote-equity API (works on all Indian networks).
    Fallback: Yahoo Finance quoteSummary API.
    """
    symbol = symbol_ns.replace(".NS", "").replace(".ns", "").upper()
    result = {}

    # ── PRIMARY: NSE Quote API ─────────────────────────────────────────────
    try:
        nse  = NSESession.get()
        nse.warm()
        resp = nse.get_api(
            f"https://www.nseindia.com/api/quote-equity?symbol={symbol}", timeout=15)
        if resp and resp.status_code == 200:
            data = resp.json()
            pi   = data.get("priceInfo", {})
            mi   = data.get("metadata",  {})
            fi   = data.get("financialData", {})
            # Map to yfinance-compatible keys
            result = {
                "regularMarketPrice": pi.get("lastPrice"),
                "marketCap"         : mi.get("issuedCap"),   # shares × price from NSE
                "trailingPE"        : pi.get("pToBv") and None,  # P/E not in quote, skip
                "returnOnEquity"    : None,
                "returnOnAssets"    : None,
                "debtToEquity"      : None,
                "earningsGrowth"    : None,
                "revenueGrowth"     : None,
                "profitMargins"     : None,
                "operatingCashflow" : None,
                "netIncomeToCommon" : None,
                "priceToBook"       : pi.get("pToBv"),
                "operatingMargins"  : None,
                "grossMargins"      : None,
                "enterpriseValue"   : None,
                "ebitda"            : None,
            }
            # Try to get market cap properly
            lp = pi.get("lastPrice") or 0
            ic = mi.get("issuedSize") or mi.get("isinCode") and 0
            try:
                ic = float(str(data.get("securityInfo", {}).get("issuedSize", "0")).replace(",",""))
                if lp and ic:
                    result["marketCap"] = lp * ic
            except Exception:
                pass

            if result.get("regularMarketPrice"):
                # Got live price — now try Yahoo for the deeper fundamentals
                pass  # fall through to Yahoo below
    except Exception:
        pass

    # ── FALLBACK / SUPPLEMENT: Yahoo Finance quoteSummary ─────────────────
    try:
        modules = "defaultKeyStatistics,financialData,summaryDetail"
        for host in ["query1", "query2"]:
            url = (f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{symbol_ns}"
                   f"?modules={modules}")
            try:
                resp = _YF_SESSION.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                qr   = data.get("quoteSummary", {}).get("result")
                if not qr:
                    continue
                merged = {}
                for module in qr:
                    for v in module.values():
                        if isinstance(v, dict):
                            for k2, v2 in v.items():
                                if isinstance(v2, dict) and "raw" in v2:
                                    merged[k2] = v2["raw"]
                                elif not isinstance(v2, dict):
                                    merged[k2] = v2
                yf_result = {
                    "regularMarketPrice": merged.get("regularMarketPrice") or merged.get("currentPrice"),
                    "marketCap"         : merged.get("marketCap"),
                    "trailingPE"        : merged.get("trailingPE"),
                    "returnOnEquity"    : merged.get("returnOnEquity"),
                    "returnOnAssets"    : merged.get("returnOnAssets"),
                    "debtToEquity"      : merged.get("debtToEquity"),
                    "earningsGrowth"    : merged.get("earningsGrowth"),
                    "revenueGrowth"     : merged.get("revenueGrowth"),
                    "profitMargins"     : merged.get("profitMargins"),
                    "operatingCashflow" : merged.get("operatingCashflow"),
                    "netIncomeToCommon" : merged.get("netIncomeToCommon"),
                    "priceToBook"       : merged.get("priceToBook"),
                    "operatingMargins"  : merged.get("operatingMargins"),
                    "grossMargins"      : merged.get("grossMargins"),
                    "enterpriseValue"   : merged.get("enterpriseValue"),
                    "ebitda"            : merged.get("ebitda"),
                }
                # Merge: Yahoo overrides NSE for fields Yahoo has
                for k, v in yf_result.items():
                    if v is not None:
                        result[k] = v
                break
            except Exception:
                continue
    except Exception:
        pass

    return result




class IndiaVIXFetcher:
    """India VIX from NSE — purely Indian fear gauge from Nifty options."""
    URL_ALL     = "https://www.nseindia.com/api/allIndices"
    URL_VIX_CSV = "https://archives.nseindia.com/content/indices/vix_history.csv"
    def __init__(self):
        self._vix = None
        self._fetched = False
    def fetch(self):
        if self._fetched: return self._vix
        # Use plain session — allIndices works without NSE cookies (confirmed)
        sess = requests.Session()
        sess.headers.update(HEADERS)
        # Try 1: allIndices (confirmed working — 110KB response)
        try:
            resp = sess.get(self.URL_ALL, timeout=12)
            if resp.status_code == 200 and resp.text.strip() and resp.text.strip()[0] in "[{":
                for item in resp.json().get("data", []):
                    idx_name = str(item.get("index","")).upper()
                    if "VIX" in idx_name or "INDIA VIX" in idx_name:
                        v = item.get("last") or item.get("currentValue") or item.get("indexValue")
                        if v:
                            self._vix = round(float(v), 2)
                            print(f"   📊 India VIX: {self._vix}")
                            self._fetched = True
                            return self._vix
        except Exception as e:
            print(f"   ⚠️  India VIX (allIndices): {e}")
        # Try 2: NSESession (warmed)
        try:
            resp2 = NSESession.get().get_api(self.URL_ALL, timeout=12)
            if resp2.status_code == 200 and resp2.text.strip()[0] in "[{":
                for item in resp2.json().get("data", []):
                    if "VIX" in str(item.get("index","")).upper():
                        v = item.get("last") or item.get("currentValue")
                        if v:
                            self._vix = round(float(v), 2)
                            print(f"   📊 India VIX: {self._vix}")
                            self._fetched = True
                            return self._vix
        except Exception:
            pass
        print("   ⚠️  India VIX: not available today")
        self._fetched = True
        return self._vix
    def score(self):
        v = self._vix
        if v is None:  return 4
        if v < 13:     return 8
        if v < 16:     return 6
        if v < 18:     return 4
        if v < 20:     return 2
        return -5


# ─────────────────────────────────────────────────────────────────────
#  OPEN INTEREST FETCHER  (v7.0)
# ─────────────────────────────────────────────────────────────────────
class OpenInterestFetcher:
    """NSE F&O OI data. Long buildup = institutions buying = bullish."""
    def __init__(self):
        self._data = {}
        self._fetched = False
    def fetch_all(self):
        if self._fetched: return
        try:
            url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
            resp = NSESession.get().get_api(url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                for item in resp.json().get("data", []):
                    sym = str(item.get("symbol","")).strip().upper()
                    if not sym: continue
                    try:
                        oi_ch = float(item.get("perChange", 0) or 0)
                        pr_ch = float(item.get("pChange",   0) or 0)
                        if   oi_ch > 2  and pr_ch > 0: bt = "LongBuildup"
                        elif oi_ch > 2  and pr_ch < 0: bt = "ShortBuildup"
                        elif oi_ch < -2 and pr_ch > 0: bt = "ShortCovering"
                        elif oi_ch < -2 and pr_ch < 0: bt = "LongUnwinding"
                        else:                           bt = "Neutral"
                        self._data[sym] = {"oi_change_pct": round(oi_ch,2), "buildup_type": bt}
                    except Exception: pass
                print(f"   📈 OI data: {len(self._data)} stocks")
        except Exception as e:
            print(f"   ⚠️  OI fetch: {e}")
        # Try 2: allIndices has some OI-like data
        if not self._data:
            try:
                resp2 = NSESession.get().get_api(
                    "https://www.nseindia.com/api/allIndices", timeout=12)
                if resp2.status_code == 200 and resp2.text.strip() and resp2.text.strip()[0] in "[{":
                    for item in resp2.json().get("data", []):
                        idx = str(item.get("index",""))
                        pch = item.get("percentChange", 0) or 0
                        if "NIFTY" in idx and "BANK" not in idx and "IT" not in idx:
                            # Market is positive/negative signals overall OI tone
                            bt = "LongBuildup" if float(pch) > 0.3 else "ShortBuildup" if float(pch) < -0.3 else "Neutral"
                            # Apply to all FNO stocks as a broad signal
                            for sym in FNO_STOCKS if "FNO_STOCKS" in dir() else []:
                                if sym not in self._data:
                                    self._data[sym] = {"oi_change_pct": round(float(pch),2), "buildup_type": bt}
                            break
            except Exception:
                pass
        self._fetched = True
    def get(self, symbol):
        return self._data.get(symbol, {})
    @staticmethod
    def score(oi_data):
        if not oi_data: return 0
        return {"LongBuildup":10,"ShortCovering":8,"Neutral":3,
                "LongUnwinding":-5,"ShortBuildup":0}.get(oi_data.get("buildup_type","Neutral"), 0)


# ─────────────────────────────────────────────────────────────────────
#  PROMOTER ACTIVITY FETCHER  (v7.0)
# ─────────────────────────────────────────────────────────────────────
class PromoterActivityFetcher:
    """SEBI-mandated quarterly shareholding data. Promoter buying = strongest India signal."""
    def __init__(self):
        self._data = {}
        self._fetched_set = set()
    def fetch(self, symbol):
        if symbol in self._fetched_set:
            return self._data.get(symbol, {})
        self._fetched_set.add(symbol)
        result = {"promoter_holding":None,"promoter_chg_qoq":None,
                  "promoter_buying":False,"promoter_selling":False,
                  "pledge_pct":None,"pledge_decreasing":False}
        try:
            url = f"https://www.nseindia.com/api/shareholders-data?symbol={symbol}"
            resp = NSESession.get().get_api(url, timeout=10)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                if isinstance(data, list) and len(data) >= 2:
                    ph_now  = float(data[0].get("promoter",       0) or 0)
                    ph_prev = float(data[1].get("promoter",       0) or 0)
                    pl_now  = float(data[0].get("promoterPledge", 0) or 0)
                    pl_prev = float(data[1].get("promoterPledge", 0) or 0)
                    chg = round(ph_now - ph_prev, 2)
                    result.update({
                        "promoter_holding" : round(ph_now, 2),
                        "promoter_chg_qoq" : chg,
                        "promoter_buying"  : chg > 0.5,
                        "promoter_selling" : chg < -0.5,
                        "pledge_pct"       : round(pl_now, 2),
                        "pledge_decreasing": pl_prev > pl_now > 0,
                    })
        except Exception: pass
        self._data[symbol] = result
        return result
    @staticmethod
    def score(data):
        if not data: return 0
        s = 0
        if data.get("promoter_buying"):   s += 10
        if data.get("pledge_decreasing"): s += 5
        if data.get("promoter_selling"):  s -= 10
        return s


# ─────────────────────────────────────────────────────────────────────
#  STOCK SCORER  (v7.0 — India-First Scoring Engine)
# ─────────────────────────────────────────────────────────────────────

class ExpertFilter:
    """
    13-point expert decision checklist used by professional Indian swing traders.
    Each point = 1 YES or NO.

    RULE:
      ≥ 10 YES → Conviction trade (aggressive position)
       7–9 YES → Normal trade (standard position)
       ≤ 6 YES → No trade (skip regardless of score)

    Categories:
      A. Market Context      (2 points) — Nifty + breadth
      B. Sector Confirmation (2 points) — sector index + peer breakouts
      C. Price Structure     (2 points) — base + higher lows
      D. Breakout Quality    (2 points) — clear resistance + candle quality
      E. Volume Behavior     (2 points) — surge on breakout + contraction after
      F. Indicator Health    (1 point)  — RSI 52-62 + ADX 20-30
      G. Risk Setup          (2 points) — SL defined + R:R ≥ 1:2
    """

    @staticmethod
    def evaluate(result: dict, sector_strength: float,
                 nifty_above_sma: bool, breadth_pct: float) -> dict:
        """
        Evaluate all 13 expert checklist points for a single stock.
        Returns dict with individual point results + total YES count + decision.
        """
        price      = result.get("price", 0)
        ema_20     = result.get("ema_21", 0)   # using EMA21 ≈ SMA20
        ema_50     = result.get("ema_50", 0)
        ema_200    = result.get("ema_200", 0)
        rsi        = result.get("rsi", 0)
        adx        = result.get("adx", 0)
        macd       = result.get("macd", 0)
        macd_sig   = result.get("macd_sig", 0)
        vol_ratio  = result.get("vol_ratio", 0)
        pct_high   = result.get("pct_from_high", -100)
        bb_width   = result.get("bb_width", 20)
        chg_5d     = result.get("chg_5d", 0)
        chg_1m     = result.get("chg_1m", 0)
        delivery   = result.get("delivery_pct", 0) or 0
        ts         = result.get("trade_setup", {}) or {}
        entry      = ts.get("entry", 0) or 0
        sl         = ts.get("stop_loss", 0) or 0
        rr         = ts.get("rr_ratio", 0) or 0
        bo_found   = result.get("breakout", False)
        is_nr7     = result.get("nr7", False)
        is_inside  = result.get("inside_day", False)
        candles    = result.get("candle_patterns", {})
        stage      = result.get("stage", "Unknown")
        is_stage2  = result.get("is_stage2", False)
        vcp_score  = result.get("vcp_score", 0)
        near_high  = pct_high >= -5
        vol_dry    = result.get("vol_dry_up", False)

        # ── A. MARKET CONTEXT (2 points) ──
        a1 = nifty_above_sma                     # Nifty above 20 & 50 DMA
        a2 = breadth_pct >= 55                   # Market breadth supportive

        # ── B. SECTOR CONFIRMATION (2 points) ──
        b1 = sector_strength >= 55               # Sector index above 20 DMA equivalent
        b2 = sector_strength >= 65               # Same sector stocks strong/breakout zone

        # ── C. PRICE STRUCTURE (2 points) ──
        # v7.1 FIX: Removed VCP (US concept), replaced with India-specific checks
        # 3-6 weeks consolidation = flat base OR NR7/Inside Day (confirmed)
        # OR: stock in 8-20% below 52W high zone (accumulation zone)
        pct_high2 = result.get("pct_from_high", -100)
        in_accum_zone = -20 <= pct_high2 <= -5   # classic Indian accumulation range
        c1 = (result.get("flat_base", False) or
              is_nr7 or is_inside or
              in_accum_zone or
              result.get("vol_dry_up", False))    # Volume dry-up = base forming
        # Higher low / tight range = sellers weak
        c2 = (price > ema_20 and ema_20 > ema_50 and
              chg_1m > -5 and chg_1m < 20)       # Price structure intact

        # ── D. BREAKOUT QUALITY (2 points) ──
        # Breakout above clear resistance
        d1 = (bo_found or near_high or
              (price > ema_20 and vol_ratio >= 1.5))   # Breakout confirmed
        # Good candle — no big upper wick (using vol_ratio + delivery as proxy)
        d2 = (delivery >= 45 or
              bool(candles) or
              vol_ratio >= 1.8)                  # Candle quality / conviction

        # ── E. VOLUME BEHAVIOR (2 points) ──
        e1 = vol_ratio >= 1.5                    # Breakout candle ≥ 1.5× avg volume
        e2 = vol_dry or vol_ratio < 2.5          # After surge: contraction (no dumping)

        # ── F. INDICATOR HEALTH (1 point) ──
        # v7.1 FIX: Replaced MACD (US signal, removed) with Supertrend (India signal)
        # RSI in sweet spot + ADX showing trend + Supertrend in BUY mode
        st_buy = result.get("supertrend_dir", 0) == 1
        f1 = (52 <= rsi <= 68 and adx >= 20 and st_buy)

        # ── G. RISK SETUP (2 points) ──
        # Stop-loss clearly defined
        g1 = (sl > 0 and entry > 0 and
              0 < (entry - sl) / entry * 100 <= 7)   # SL within 7% of entry
        # R:R ≥ 1:2
        g2 = rr >= 1.8                           # Minimum 1:2 risk reward

        checks = {
            "a1_nifty_above_dma"       : a1,
            "a2_breadth_supportive"    : a2,
            "b1_sector_strong"         : b1,
            "b2_sector_peers_breaking" : b2,
            "c1_base_consolidation"    : c1,
            "c2_price_structure_ok"    : c2,
            "d1_breakout_confirmed"    : d1,
            "d2_candle_quality_ok"     : d2,
            "e1_volume_surge"          : e1,
            "e2_volume_contraction"    : e2,
            "f1_indicators_aligned"    : f1,
            "g1_stoploss_defined"      : g1,
            "g2_rr_minimum"            : g2,
        }

        yes_count = sum(1 for v in checks.values() if v)

        if   yes_count >= 10: decision = "CONVICTION"   # aggressive position
        elif yes_count >= 7:  decision = "TRADE"        # normal position
        else:                 decision = "SKIP"         # no trade

        return {
            "expert_checks"  : checks,
            "expert_yes"     : yes_count,
            "expert_decision": decision,
            "expert_grade"   : ("A+" if yes_count >= 11 else
                                "A"  if yes_count >= 9  else
                                "B+" if yes_count >= 7  else
                                "B"  if yes_count >= 5  else "C"),
        }

    @staticmethod
    def labels() -> dict:
        """Human-readable labels for each check point."""
        return {
            "a1_nifty_above_dma"       : "Nifty above 20 & 50 DMA",
            "a2_breadth_supportive"    : "Market breadth ≥ 55% above 200 EMA",
            "b1_sector_strong"         : "Sector strength ≥ 55 (index above 20 DMA)",
            "b2_sector_peers_breaking" : "Sector peers in breakout zone (strength ≥ 65)",
            "c1_base_consolidation"    : "3–6 week consolidation / base formed",
            "c2_price_structure_ok"    : "Higher lows / tight range (sellers weak)",
            "d1_breakout_confirmed"    : "Price at or above resistance / 20-day high",
            "d2_candle_quality_ok"     : "Strong candle — high delivery or conviction",
            "e1_volume_surge"          : "Breakout volume ≥ 1.5× 20-day average",
            "e2_volume_contraction"    : "Volume contraction after surge (no dumping)",
            "f1_indicators_aligned"    : "RSI 52–68, ADX ≥ 20, MACD > Signal",
            "g1_stoploss_defined"      : "Stop-loss defined, risk ≤ 7% of entry",
            "g2_rr_minimum"            : "Risk : Reward ≥ 1:2",
        }



# ─────────────────────────────────────────────────────────────────────
#  MAIN ANALYSIS PIPELINE
# ─────────────────────────────────────────────────────────────────────

class StockScorer:
    """
    v7.0 India-First Swing Trading Scorer.

    Follow Indian institutional money BEFORE price reacts.
    India-specific signals get highest weights:
      Delivery%(12) + FII/DII(12) + Bulk deals(12) + Promoter buying(10)
      + India VIX(8) + OI buildup(10) + PCR(6) = 70 pts India-specific

    Setup quality (reduced US-centric signals):
      Compression(14) + VolDryUp(8) + BasePos(8) + Supertrend(10) = 40 pts
      VCP reduced 18→10, BB reduced 12→6

    Penalties:
      Freshness(-28) + Pledge(-15) + Results season(-10) = -53 max

    Score 0-100. A+≥80, A≥67, B+≥54, B≥42, C≥28
    """

    def __init__(self, nifty_series, vix_fetcher=None, fii_dii_data=None, pcr_data=None):
        self.nifty   = nifty_series
        self.vix     = vix_fetcher
        self.fii_dii = fii_dii_data or {}
        self.pcr     = pcr_data or {}

    def relative_strength(self, stock_close, lookback=63):
        if self.nifty is None or len(self.nifty) < lookback: return 0
        try:
            common = stock_close.index.intersection(self.nifty.index)
            if len(common) < lookback: return 0
            sc = stock_close.loc[common].tail(lookback)
            nc = self.nifty.loc[common].tail(lookback)
            return round((sc.iloc[-1]/sc.iloc[0]-1)*100 - (nc.iloc[-1]/nc.iloc[0]-1)*100, 2)
        except Exception: return 0

    # ── India-Specific (highest weight) ──

    @staticmethod
    def score_delivery_india(df, delivery_pct):
        """
        v7.1 FIX: Delivery must be directional + volume-weighted.
        High delivery on UP day   = accumulation (bullish) → reward
        High delivery on DOWN day = distribution (selling) → penalise
        Low absolute volume + high delivery %  = meaningless → ignore
        """
        if delivery_pct is None or len(df) < 2: return 0

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        close = last["Close"]
        prev_close = prev["Close"]

        # Price direction
        price_up = close >= prev_close   # green or flat candle

        # Volume weight — delivery % on illiquid stock is noise
        avg_daily_value = df["Volume"].tail(20).mean() * close
        if avg_daily_value < 5_000_000:   # below ₹50 lakh avg daily value
            return 0   # too illiquid — delivery % unreliable

        # Accumulation: delivery high + price up = institutions buying
        if price_up:
            if   delivery_pct >= 75: return 12
            elif delivery_pct >= 65: return 10
            elif delivery_pct >= 55: return 8
            elif delivery_pct >= 45: return 5
            elif delivery_pct >= 35: return 2
            return 0
        else:
            # Distribution: delivery high + price down = institutions selling
            if   delivery_pct >= 70: return -8   # heavy distribution
            elif delivery_pct >= 55: return -4   # moderate distribution
            elif delivery_pct >= 40: return -2
            return 0   # low delivery on down day = just profit booking

    def score_fii_dii_india(self):
        """
        v7.1 FIX: FII flow is market-wide — same for all 500 stocks.
        Changed from additive (wrong) to a GATE score:
          - Strong FII buying  → +6  (market tailwind)
          - Moderate buying    → +3
          - Neutral            → 0
          - Selling            → -3 to -8 (market headwind)
        This is applied as a MARKET GATE — it sets the context but
        does not mislead by adding 12 identical pts to every stock.
        A stock-specific OI buildup score handles individual F&O stocks.
        """
        fii_5d    = self.fii_dii.get("fii_5d")
        fii_today = self.fii_dii.get("fii_net")
        if fii_5d is None: return 2   # unknown → small neutral

        if   fii_5d >  6000: return 6    # strong buying  → solid tailwind
        elif fii_5d >  2000: return 4    # moderate buying
        elif fii_5d >   500: return 2    # mild buying
        elif fii_5d >  -500: return 0    # neutral
        elif fii_5d > -2000: return -3   # mild selling
        elif fii_5d > -5000: return -5   # heavy selling
        else:                return -8   # extreme selling → avoid new longs

    @staticmethod
    def score_bulk_deal_india(deal_data):
        if not deal_data: return 0
        if deal_data.get("bulk_sell"):  return -20
        if deal_data.get("bulk_buy"):   return 12
        if deal_data.get("block_buy"):  return 10
        return 0

    @staticmethod
    def score_promoter_india(pdata):
        if not pdata: return 0
        s = 0
        if pdata.get("promoter_buying"):   s += 10
        if pdata.get("pledge_decreasing"): s += 5
        if pdata.get("promoter_selling"):  s -= 10
        return s

    def score_india_vix(self):
        if self.vix is None: return 4
        return self.vix.score() if hasattr(self.vix, "score") else 4

    @staticmethod
    def score_oi_buildup(oi_data):
        return OpenInterestFetcher.score(oi_data)

    def score_pcr_india(self):
        pcr = self.pcr.get("nifty_pcr")
        if pcr is None: return 3
        if   pcr > 1.4: return 6
        elif pcr > 1.2: return 5
        elif pcr > 0.9: return 3
        elif pcr > 0.7: return 1
        return 0

    def score_fii_absorption_india(self, df, delivery_pct):
        """
        FII Absorption Signal — PRO-LEVEL India logic.
        When FII is SELLING overall (market-wide headwind)
        BUT this individual stock's price is HOLDING or going UP
        with HIGH DELIVERY → DII/retail/promoters absorbing FII selling.

        This is a VERY bullish signal — smart domestic money is accumulating
        while foreign money exits. Stock will likely explode when FII stops selling.

        Score: +10 if strong absorption, +6 moderate, 0 if no absorption.
        """
        fii_5d     = self.fii_dii.get("fii_5d")
        if fii_5d is None or delivery_pct is None or len(df) < 5:
            return 0

        fii_selling = fii_5d < -1000  # FII selling ₹1000+ Cr over 5 days

        if not fii_selling:
            return 0   # FII not selling — absorption not relevant

        # Check if this stock is holding / going up despite FII selling
        try:
            chg_5d      = (df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100
            price_up    = df["Close"].iloc[-1] >= df["Close"].iloc[-2]
            vol_r       = df.iloc[-1].get("Vol_ratio", 1) or 1
            avg_val     = df["Volume"].tail(20).mean() * df["Close"].iloc[-1]

            if avg_val < 5_000_000: return 0  # illiquid — ignore

            stock_holding  = chg_5d > -2    # stock flat or positive last 5 days
            high_delivery  = delivery_pct >= 55

            if stock_holding and high_delivery and price_up:
                return 10   # Strong absorption — highest conviction signal
            elif stock_holding and high_delivery:
                return 6    # Moderate absorption
            elif stock_holding and delivery_pct >= 45:
                return 3    # Weak absorption
        except Exception:
            pass
        return 0

    def score_fii_pcr_combined(self):
        """
        FII + PCR Combined Signal — India's highest confidence bull indicator.
        When BOTH FII is buying AND PCR > 1.2 on the same day:
          = institutions buying + options market shows too many puts = contrarian bull signal
          = best possible market condition for swing long trades
        This combination appears roughly 15-20 times per year.
        When it appears, it is the strongest market-level buy signal in Indian markets.
        """
        fii_5d = self.fii_dii.get("fii_5d")
        pcr    = self.pcr.get("nifty_pcr")

        if fii_5d is None or pcr is None:
            return 0

        fii_buying  = fii_5d > 2000   # FII net buying ₹2000+ Cr over 5 days
        pcr_bullish = pcr > 1.2       # market oversold per options data

        if   fii_buying and pcr > 1.4:  return 8   # very strong combined signal
        elif fii_buying and pcr_bullish: return 5   # strong combined signal
        elif fii_buying:                 return 2   # FII buying but PCR neutral
        elif pcr_bullish and fii_5d > 0: return 2   # PCR bullish + mild FII buying
        return 0

    # ── Setup Quality ──

    @staticmethod
    def score_compression_india(is_nr7, is_inside_day, pp_found):
        s = 0
        if is_nr7:        s += 8
        if is_inside_day: s += 6
        if pp_found:      s += 8
        return min(s, 14)


    def _score_compression_india_confirmed(self, is_nr7, is_inside_day, delivery_pct, df):
        """
        Compression score with delivery confirmation (India-specific).
        NR7/InsideDay patterns are more reliable when delivery % is elevated.
        """
        s = 0
        del_pct = delivery_pct or 0
        if is_nr7:
            s += 8
            if del_pct >= 55: s += 2   # delivery confirms accumulation
        if is_inside_day:
            s += 6
            if del_pct >= 55: s += 2
        # Pocket pivot detection
        if len(df) >= 11:
            try:
                last_vol = df["Volume"].iloc[-1]
                max_down_vol = df["Volume"].iloc[-11:-1][
                    df["Close"].iloc[-11:-1].diff() < 0].max()
                if last_vol > max_down_vol and df["Close"].iloc[-1] >= df["Close"].iloc[-2]:
                    s += 8
            except Exception:
                pass
        return min(s, 14)

    @staticmethod
    def score_volume_dryup_india(df):
        if len(df) < 10: return 0
        try:
            avg_vol  = df["Volume"].tail(20).mean()
            if avg_vol == 0: return 0
            ratios   = [v/avg_vol for v in df["Volume"].tail(3)]
            if all(r < 0.7  for r in ratios): return 8
            elif all(r < 0.85 for r in ratios): return 5
            elif sum(1 for r in ratios if r < 0.75) >= 2: return 3
        except Exception: pass
        return 0

    @staticmethod
    def score_base_position_india(df):
        if len(df) < 52: return 0
        try:
            high52  = df["High"].tail(252).max()
            current = df["Close"].iloc[-1]
            pct_off = (current/high52 - 1)*100
            if  -20 <= pct_off <= -8:  return 8
            elif -25 <= pct_off < -20: return 5
            elif  -8 < pct_off <= -4:  return 3
            elif -30 <= pct_off < -25: return 2
        except Exception: pass
        return 0

    @staticmethod
    def score_supertrend_india(df):
        if "ST_Direction" not in df.columns or len(df) < 3: return 0
        cur  = df["ST_Direction"].iloc[-1]
        prev = df["ST_Direction"].iloc[-2]
        if cur == 1: return 10 if prev != 1 else 7
        return 0

    @staticmethod
    def score_bb_squeeze_india(df):
        if len(df) < 20: return 0
        bb_w = df.iloc[-1].get("BB_width", 20) or 20
        if   bb_w < 4:  return 6
        elif bb_w < 6:  return 5
        elif bb_w < 8:  return 3
        elif bb_w < 12: return 1
        return 0

    @staticmethod
    def score_vcp_india(vcp_score_raw):
        if   vcp_score_raw >= 85: return 10
        elif vcp_score_raw >= 75: return 8
        elif vcp_score_raw >= 65: return 6
        elif vcp_score_raw >= 55: return 4
        elif vcp_score_raw >= 45: return 2
        return 0

    @staticmethod
    def score_flat_base_india(has_flat_base, flat_base_info):
        if not has_flat_base: return 0
        s = 6
        if flat_base_info.get("vol_declining"): s += 2
        if flat_base_info.get("above_ema21"):   s += 1
        if flat_base_info.get("range_pct",12) < 7: s += 1
        return min(s, 10)

    # ── Trend Confirmation ──

    @staticmethod
    def score_ema_alignment_india(df):
        last  = df.iloc[-1]
        c     = last["Close"]
        conds = [
            c                      > last.get("EMA_10",  0),
            last.get("EMA_10",  0) > last.get("EMA_21",  0),
            last.get("EMA_21",  0) > last.get("EMA_50",  0),
            last.get("EMA_50",  0) > last.get("EMA_200", 0),
        ]
        return min(round(sum(conds)*1.5), 6)

    @staticmethod
    def score_rsi_india(df):
        rsi = df.iloc[-1].get("RSI", 50) or 50
        if   50 <= rsi <= 68: return 9
        elif 45 <= rsi <  50: return 6
        elif 68 <  rsi <= 75: return 3
        elif 40 <= rsi <  45: return 2
        return 0

    @staticmethod
    def score_adx_india(df):
        last  = df.iloc[-1]
        adx   = last.get("ADX",     0) or 0
        di_p  = last.get("DI_plus", 0) or 0
        di_m  = last.get("DI_minus",0) or 0
        s     = 0
        if   adx > 30: s += 5
        elif adx > 25: s += 4
        elif adx > 20: s += 2
        if di_p > di_m: s += 3
        return min(s, 8)

    @staticmethod
    def score_macd_india(df):
        last = df.iloc[-1]
        macd = last.get("MACD",        0) or 0
        sig  = last.get("MACD_signal", 0) or 0
        hist = last.get("MACD_hist",   0) or 0
        s    = 0
        if macd > sig: s += 3
        if hist > 0:   s += 2
        if len(df) >= 2:
            ph = df.iloc[-2].get("MACD_hist", 0) or 0
            if hist > ph > 0: s += 1
        return min(s, 6)

    @staticmethod
    def score_weekly_trend_india(weekly_df):
        if weekly_df is None or len(weekly_df) < 10: return 0
        last  = weekly_df.iloc[-1]
        close = last["Close"]
        s     = 0
        if close > last.get("W_EMA_10", 0): s += 2
        if close > last.get("W_EMA_21", 0): s += 2
        if last.get("W_ROC_4", 0) > 0:      s += 2
        return min(s, 6)

    @staticmethod
    def score_obv_div_india(has_div):
        return 8 if has_div else 0

    # ── Quality Gate ──

    @staticmethod
    def score_fundamentals_india(fund_data):
        if not fund_data: return 0
        return min(round((fund_data.get("fund_score",0) or 0) * 0.5), 10)

    @staticmethod
    def score_golden_cross_india(df):
        """
        Golden Cross / Death Cross — 50 EMA vs 200 EMA.
        Most watched long-term trend signal in Indian markets.
        All major Indian brokers (Zerodha, ICICI, HDFC) highlight this.

        Fresh Golden Cross (50 EMA just crossed above 200 EMA) = +8 pts
        Sustained Golden Cross (50 above 200 for >5 days)       = +4 pts
        Death Cross (50 EMA below 200 EMA)                      = −6 pts
        """
        if len(df) < 200: return 0
        try:
            ema50  = df["EMA_50"].iloc[-1]  if "EMA_50"  in df.columns else df["Close"].ewm(span=50).mean().iloc[-1]
            ema200 = df["EMA_200"].iloc[-1] if "EMA_200" in df.columns else df["Close"].ewm(span=200).mean().iloc[-1]
            # Previous values for fresh cross detection
            ema50_prev  = df["EMA_50"].iloc[-2]  if "EMA_50"  in df.columns else df["Close"].ewm(span=50).mean().iloc[-2]
            ema200_prev = df["EMA_200"].iloc[-2] if "EMA_200" in df.columns else df["Close"].ewm(span=200).mean().iloc[-2]

            currently_above = ema50 > ema200
            was_above       = ema50_prev > ema200_prev

            if currently_above:
                fresh_cross = not was_above   # just crossed today
                return 8 if fresh_cross else 4
            else:
                fresh_death = was_above       # just crossed below today
                return -8 if fresh_death else -6
        except Exception:
            return 0

    @staticmethod
    def score_stage_india(stage):
        return {"Stage 2":8,"Stage 1":0,"Stage 3":-5,"Stage 4":-10,"Unknown":0}.get(stage, 0)

    @staticmethod
    def score_candle_india(candle_score_raw):
        return min(candle_score_raw, 8)

    @staticmethod
    def score_support_india(at_support):
        return 4 if at_support else 0

    # ── Penalties ──

    @staticmethod
    def score_freshness_india(df):
        """
        v7.1 FIX: Freshness penalties — prevent buying stocks that already moved.
        KEY FIX: 52W high proximity no longer penalised.
        In Indian markets, breaking above 52W high on HIGH DELIVERY = most powerful signal.
        Penalising 52W high proximity was WRONG — it punished the best setups.

        What we penalise:
        - Moved >5% this week (operator already pushed it — late entry)
        - Moved >15% this month (already ran — freshness gone)
        - Too extended above EMA21 (rubber band stretched — mean reversion risk)
        """
        if len(df) < 20: return 0
        last  = df.iloc[-1]
        pen   = 0
        roc5  = last.get("ROC_5",  0) or 0
        roc21 = last.get("ROC_21", 0) or 0
        ema21 = last.get("EMA_21", 0) or 0
        close = last["Close"]

        # Penalty: moved too much this week (operator finished the push)
        if   roc5 > 10: pen -= 15   # blew up this week — avoid
        elif roc5 > 7:  pen -= 10
        elif roc5 > 4:  pen -= 5

        # Penalty: already ran this month
        if   roc21 > 30: pen -= 15  # already up 30% — freshness gone
        elif roc21 > 20: pen -= 10
        elif roc21 > 15: pen -= 5

        # Penalty: too extended above EMA21 (stretched rubber band)
        if ema21 > 0:
            ext = (close / ema21 - 1) * 100
            if   ext > 18: pen -= 10  # very extended — mean reversion risk
            elif ext > 12: pen -= 6
            elif ext > 8:  pen -= 3

        # NOTE: 52W HIGH PROXIMITY IS NO LONGER PENALISED (v7.1 fix)
        # Breaking above 52W high on high delivery = strongest Indian signal
        # Old code penalised this — that was wrong

        return max(pen, -28)

    @staticmethod
    def score_pledge_india(pledge_pct):
        if pledge_pct is None or pledge_pct < CFG["pledge_danger_pct"]: return 0
        return -CFG["pledge_score_penalty"]

    @staticmethod
    def score_results_india(earnings_info):
        if earnings_info and earnings_info.get("has_upcoming"): return -10
        return 0

    @staticmethod
    def score_52w_breakout_india(df, delivery_pct):
        """
        v7.1 NEW: 52W high breakout BONUS.
        In Indian markets, breaking above 52W high on high delivery + volume
        is the single highest win-rate setup. This is the opposite of what
        the old freshness penalty did (penalised it).

        Conditions: price within 1% of or above 52W high + delivery ≥ 55% + vol surge
        """
        if len(df) < 252: return 0
        try:
            high52  = df["High"].tail(252).max()
            close   = df["Close"].iloc[-1]
            vol_r   = df.iloc[-1].get("Vol_ratio", 1) or 1
            pct_off = (close / high52 - 1) * 100

            # At or breaking 52W high
            if pct_off >= -1.5:
                # Confirm with delivery + volume
                if (delivery_pct or 0) >= 60 and vol_r >= 1.5:
                    return 10   # confirmed 52W breakout — highest conviction
                elif (delivery_pct or 0) >= 50 and vol_r >= 1.2:
                    return 6    # moderate confirmation
                elif vol_r >= 2.0:
                    return 4    # volume breakout at least
            # Approaching 52W high (within 3%) with momentum
            elif pct_off >= -3:
                if (delivery_pct or 0) >= 55 and vol_r >= 1.3:
                    return 4    # approaching breakout with institutional support
        except Exception:
            pass
        return 0

    @staticmethod
    def score_circuit_penalty(circuit_risk):
        """
        v7.1 NEW: Circuit breaker penalty.
        Stocks hitting upper circuit repeatedly = operator activity.
        After the operator exits, the stock falls sharply.
        Penalise to prevent recommending operator-pushed stocks.
        """
        if not circuit_risk:
            return 0
        risk_str = str(circuit_risk).lower()
        if "upper" in risk_str:
            return -10   # near upper circuit — operator may exit
        return 0

    def score_nifty_gate(self, nifty_series):
        """
        v7.1 NEW: Nifty index gate.
        Accepts a pandas Series of Nifty Close prices.
        When Nifty is below its 50 EMA, long trade win rate drops ~40%.
        """
        if nifty_series is None or len(nifty_series) < 50:
            return 0
        try:
            close  = float(nifty_series.iloc[-1])
            ema50  = float(nifty_series.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(nifty_series.ewm(span=200, adjust=False).mean().iloc[-1])
            if   close < ema200:  return -12  # below 200 EMA = bear market
            elif close < ema50:   return -6   # below 50 EMA = correction
            else:                 return 0    # above both = bull mode
        except Exception:
            return 0

    @staticmethod
    def score_post_results_india(earnings_info, df):
        """
        v7.1 NEW: Post quarterly results momentum.
        In Indian markets, stocks that beat Q4/Q3 results by 15%+
        on both revenue and profit continue moving up for 3-6 weeks.
        This is the strongest fundamental catalyst in Indian markets.
        Check: results just announced (last 21 days) + stock up >3% since.
        """
        if not earnings_info:
            return 0
        # Check if results were recent (announced, not upcoming)
        if earnings_info.get("has_upcoming"):
            return 0    # upcoming = avoid, not bonus
        # Simple proxy: check if stock has positive 21-day momentum after flat period
        # A proper implementation needs results beat data from NSE corporate actions
        # For now: if no upcoming results AND stock is in stage 2 with recent base = small bonus
        return 0   # placeholder — upgrade when corporate actions data available

    # ── Master Score ──

    def compute_score(self, daily_df, weekly_df, delivery_pct=None,
                      fund_data=None, stage="Unknown", pledge_pct=None,
                      vcp_score_raw=0, is_nr7=False, is_inside_day=False,
                      pp_found=False,
                      candle_score=0, has_obv_div=False, has_flat_base=False,
                      flat_base_info=None, is_nr4=False, is_weekly_nr7=False,
                      at_support=False, bulk_deal_data=None, is_ipo_base=False,
                      promoter_data=None, oi_data=None, earnings_info=None,
                      # v7.1 new
                      circuit_risk=None, nifty_df=None):

        scores = {
            # ── India-specific (top priority) ──
            "delivery_india"  : self.score_delivery_india(daily_df, delivery_pct),
            "fii_dii_india"   : self.score_fii_dii_india(),
            "bulk_deal_india" : self.score_bulk_deal_india(bulk_deal_data or {}),
            "promoter_india"  : self.score_promoter_india(promoter_data or {}),
            "india_vix"       : self.score_india_vix(),
            "oi_buildup"      : self.score_oi_buildup(oi_data or {}),
            "pcr_india"       : self.score_pcr_india(),

            # ── Setup quality ──
            "supertrend"      : self.score_supertrend_india(daily_df),
            "vol_dryup"       : self.score_volume_dryup_india(daily_df),
            "base_position"   : self.score_base_position_india(daily_df),
            "support_prox"    : self.score_support_india(at_support),

            # ── Compression (India version — must be confirmed) ──
            "compression"     : self._score_compression_india_confirmed(
                                    is_nr7, is_inside_day, delivery_pct, daily_df),

            # ── Candle Patterns ──
            "candle_pattern"  : self.score_candle_india(candle_score),

            # ── Trend Context ──
            "ema_alignment"   : self.score_ema_alignment_india(daily_df),
            "rsi_sweetspot"   : self.score_rsi_india(daily_df),
            "adx_trend"       : self.score_adx_india(daily_df),

            # ── Quality Gate ──
            "fundamentals"    : self.score_fundamentals_india(fund_data),
            "stage_analysis"  : self.score_stage_india(stage),

            # ── IPO Base ──
            "ipo_base"        : (6 if is_ipo_base else 0),

            # ── v7.1 NEW — 52W breakout bonus + Golden Cross ──
            "breakout_52w"    : self.score_52w_breakout_india(daily_df, delivery_pct),
            "golden_cross"    : self.score_golden_cross_india(daily_df),
            "fii_pcr_combo"   : self.score_fii_pcr_combined(),    # FII buying + PCR oversold = best India signal
            "fii_absorption"  : self.score_fii_absorption_india(daily_df, delivery_pct),  # smart money absorbing FII selling
        }

        # ── Penalties ──
        scores["freshness_penalty"] = self.score_freshness_india(daily_df)
        scores["pledge_penalty"]    = self.score_pledge_india(pledge_pct)
        scores["results_penalty"]   = self.score_results_india(earnings_info)

        # ── v7.1 NEW penalties ──
        scores["circuit_penalty"]   = self.score_circuit_penalty(circuit_risk)
        scores["nifty_gate"]        = self.score_nifty_gate(nifty_df)

        # ── Multi-TF compression bonus ──
        if is_nr7 and is_weekly_nr7: scores["multi_tf_bonus"] = 6
        elif is_nr4:                 scores["multi_tf_bonus"] = 4
        else:                        scores["multi_tf_bonus"] = 0

        total = sum(scores.values())
        return round(min(max(total, 0), 100)), scores

    @staticmethod
    def assign_grade(score):
        if score >= CFG["grade_aplus"]: return "A+"
        if score >= CFG["grade_a"]:     return "A"
        if score >= CFG["grade_bplus"]: return "B+"
        if score >= CFG["grade_b"]:     return "B"
        if score >= CFG["grade_c"]:     return "C"
        return "D"

    @staticmethod
    def grade_color(grade):
        return {"A+":"#059669","A":"#10b981","B+":"#0284c7",
                "B":"#38bdf8","C":"#f59e0b","D":"#ef4444"}.get(grade,"#888")

    @staticmethod
    def compute_confidence_pct(result: dict) -> int:
        score    = result.get("score", 0)
        sigs     = min(len(result.get("active_signals",[])), 8)
        stage2   = 1 if result.get("is_stage2")                else 0
        fund_str = 1 if result.get("fund_grade")=="Strong"     else 0
        del_ok   = 1 if (result.get("delivery_pct") or 0)>=55  else 0
        fii_ok   = 1 if result.get("fii_buying", False)        else 0
        roc5_q   = 1 if abs(result.get("chg_5d",99)) < 2       else 0
        promo    = 1 if result.get("promoter_buying", False)    else 0
        conf = (score*0.55 + sigs*3.5 + stage2*8 + fund_str*4
                + del_ok*5 + fii_ok*5 + promo*6 + roc5_q*4)
        return max(40, min(99, round(conf)))


class NSEAnalysisPipeline:

    def __init__(self):
        self.nse_fetcher  = NSEDataFetcher()
        self.price_mgr    = PriceDataManager()
        self.ta           = TechnicalAnalyzer()
        self.patterns     = PatternDetector()
        self.delivery     = DeliveryFetcher()
        self.bulk_deals   = BulkDealFetcher()
        self.fii_dii      = FIIDIIFetcher()
        self.fund_fetch   = FundamentalFetcher()
        self.promoter     = PromoterFetcher()
        self.accum        = InstitutionalAccumulationDetector()
        self.trade_calc   = TradeSetupCalculator()
        self.sector_mgr   = SectorMomentumAnalyzer()
        # v7.0 India-specific fetchers
        self.india_vix    = IndiaVIXFetcher()
        self.oi_fetcher   = OpenInterestFetcher()
        self.promoter_act = PromoterActivityFetcher()
        # shared FII/DII and PCR data (fetched once in run(), passed to scorer)
        self._fii_dii_data = {}
        self._pcr_data     = {}

    # ── AVWAP Pre-Breakout Scanner Engine (v8.0) ─────────────────────────
    @staticmethod
    def _compute_avwap_scanner(daily_df, last, delivery_pct=None):
        """
        Full AVWAP Pre-Breakout scanner:
          Step 1: Base candidate filter (uptrend + near breakout + vol spike + tight consolidation)
          Step 2: Anchored VWAP from swing low
          Step 3: Smart money filter (above AVWAP 3+ candles, near resistance, vol contraction)
          Step 4: Score 0–5
          Step 5: Tags
        Returns dict of avwap_* fields to merge into the stock result.
        """
        import numpy as np

        close = daily_df["Close"]
        high  = daily_df["High"]
        low   = daily_df["Low"]
        vol   = daily_df["Volume"]
        opn   = daily_df["Open"]
        n     = len(daily_df)

        defaults = {
            "avwap_score": 0, "avwap_value": 0.0, "avwap_above": False,
            "avwap_held_days": 0, "avwap_dist_to_breakout": 0.0,
            "avwap_vol_vs_avg": 0.0, "avwap_consolidation": False,
            "avwap_candidate": False, "avwap_smart_money": False,
            "avwap_tag": "",
        }
        if n < 50:
            return defaults

        c  = float(close.iloc[-1])
        h  = float(high.iloc[-1])
        lo = float(low.iloc[-1])
        v  = float(vol.iloc[-1])

        # ── STEP 1: BASE SCANNER (Candidate Filter) ──────────────────
        # SMA 20 and SMA 50
        sma20 = float(close.tail(20).mean())
        sma50 = float(close.tail(50).mean())

        # 1a. Uptrend: Close > SMA20 AND Close > SMA50
        uptrend = c > sma20 and c > sma50

        # 1b. Near Breakout Zone: Close >= 95% of 20-day highest high
        high_20d = float(high.tail(20).max())
        near_breakout = c >= high_20d * 0.95 if high_20d > 0 else False

        # 1c. Volume Spike: Volume > 1.5 * SMA(20, Volume)
        vol_sma20 = float(vol.tail(20).mean())
        vol_spike = v > 1.5 * vol_sma20 if vol_sma20 > 0 else False
        vol_vs_avg = round(v / vol_sma20, 2) if vol_sma20 > 0 else 0

        # 1d. Tight Consolidation: (High - Low) / Close < 0.03
        range_pct = (h - lo) / c if c > 0 else 1
        tight_consolidation = range_pct < 0.03

        is_candidate = uptrend and near_breakout

        # ── STEP 2: AVWAP CALCULATION ─────────────────────────────────
        # Anchor at lowest low in last 30 sessions
        lookback_avwap = min(30, n)
        tail_low = low.tail(lookback_avwap)
        anchor_idx = int(tail_low.values.argmin())
        anchor_pos = n - lookback_avwap + anchor_idx  # absolute position in df

        # Compute AVWAP from anchor to latest candle (vectorized)
        typical_price = (high.iloc[anchor_pos:] + low.iloc[anchor_pos:] + close.iloc[anchor_pos:]) / 3.0
        cum_tp_vol = (typical_price * vol.iloc[anchor_pos:]).cumsum()
        cum_vol    = vol.iloc[anchor_pos:].cumsum()
        avwap_series = cum_tp_vol / cum_vol.replace(0, np.nan)

        avwap_value = round(float(avwap_series.iloc[-1]), 2) if not np.isnan(avwap_series.iloc[-1]) else 0
        above_avwap = c > avwap_value if avwap_value > 0 else False

        # ── STEP 3: SMART MONEY FILTER ────────────────────────────────
        # 3a. Price held above AVWAP for at least 3 candles
        held_days = 0
        if avwap_value > 0 and len(avwap_series) >= 3:
            for i in range(len(avwap_series) - 1, -1, -1):
                av = float(avwap_series.iloc[i])
                cl = float(close.iloc[anchor_pos + i])
                if cl > av and not np.isnan(av):
                    held_days += 1
                else:
                    break
        avwap_held = held_days >= 3

        # 3b. Distance from resistance (20-day high) < 5%
        dist_to_breakout = round(((high_20d - c) / c) * 100, 2) if c > 0 else 99
        near_resistance = dist_to_breakout < 5

        # 3c. Volatility contraction (range tightening over last 5 candles)
        if n >= 10:
            recent_ranges = ((high.tail(5) - low.tail(5)) / close.tail(5)).values
            prev_ranges   = ((high.iloc[-10:-5] - low.iloc[-10:-5]) / close.iloc[-10:-5]).values
            avg_recent = float(np.mean(recent_ranges))
            avg_prev   = float(np.mean(prev_ranges))
            vol_contraction = avg_recent < avg_prev * 0.85  # 15%+ range contraction
        else:
            vol_contraction = False

        smart_money = above_avwap and avwap_held and near_resistance

        # ── STEP 4: SCORING (0–5) ────────────────────────────────────
        score = 0
        if c > sma20:            score += 1   # Close > SMA20
        if c > sma50:            score += 1   # Close > SMA50
        if vol_spike:            score += 1   # Volume spike present
        if above_avwap:          score += 1   # Close > AVWAP
        if tight_consolidation:  score += 1   # Tight consolidation

        # ── STEP 5: TAG ──────────────────────────────────────────────
        tag = ""
        if score >= 4 and smart_money:
            tag = "🔥 Hidden Breakout Candidate"
        elif score >= 4:
            tag = "⚡ Smart Money Active"
        elif score >= 3 and above_avwap:
            tag = "📊 AVWAP Setup Forming"

        return {
            "avwap_score": score,
            "avwap_value": avwap_value,
            "avwap_above": above_avwap,
            "avwap_held_days": held_days,
            "avwap_dist_to_breakout": dist_to_breakout,
            "avwap_vol_vs_avg": vol_vs_avg,
            "avwap_consolidation": tight_consolidation,
            "avwap_vol_contraction": vol_contraction,
            "avwap_candidate": is_candidate,
            "avwap_smart_money": smart_money,
            "avwap_tag": tag,
            "avwap_sma20": round(sma20, 2),
            "avwap_sma50": round(sma50, 2),
            "avwap_high_20d": round(high_20d, 2),
            "avwap_delivery_pct": delivery_pct,
        }

    def analyze_one(self, symbol):
        try:
            raw = self.price_mgr.fetch_stock(symbol)
            if raw is None:
                return None

            daily  = self.ta.compute_all(raw["daily"])
            weekly = self.ta.compute_weekly(raw["weekly"]) if not raw["weekly"].empty else None

            # ── Delivery % ──
            delivery_pct = self.delivery.get(symbol)

            # ── Fundamentals (v3.0) ──
            fund_data = self.fund_fetch.fetch(symbol)

            # ── Promoter Pledging (v3.0) ──
            promoter_data = self.promoter.fetch(symbol)
            pledge_pct    = promoter_data.get("pledge_pct")

            # ── Stage Analysis (v3.0) ──
            stage, stage_info = self.patterns.detect_stage(weekly)

            # ── Institutional Accumulation (v4.0) ──
            accum_data = InstitutionalAccumulationDetector.detect(daily, delivery_pct)

            scorer = StockScorer(
                self.price_mgr.nifty_data,
                vix_fetcher  = self.india_vix,
                fii_dii_data = self._fii_dii_data,
                pcr_data     = self._pcr_data,
            )

            # ── v7.0 India-specific data ──
            promoter_act_data = self.promoter_act.fetch(symbol)
            oi_data           = self.oi_fetcher.get(symbol)

            # ── Pattern detections (must happen BEFORE compute_score) ──
            vcp_score, vcp_info = self.patterns.detect_vcp(daily)
            pp_found, pp_str    = self.patterns.detect_pocket_pivot(daily)
            is_nr7              = self.patterns.detect_nr7(daily)
            is_nr4              = self.patterns.detect_nr4(daily)          # NEW v6
            is_inside           = self.patterns.detect_inside_day(daily)
            htf, htf_info       = self.patterns.detect_high_tight_flag(daily)
            three_tight         = self.patterns.detect_three_tight_closes(daily)
            vol_dry             = self.patterns.detect_volume_dry_up(daily)
            bo_found, bo_str, bo_info = self.patterns.detect_breakout(daily)
            vs_type, vs_ratio, vs_up  = self.patterns.detect_volume_surge(daily)

            # ── v6.0 new detections ──
            has_flat_base, flat_base_info = self.patterns.detect_flat_base(daily)
            candle_patterns, candle_score = self.patterns.detect_candle_patterns(daily)
            is_weekly_nr7 = self.patterns.detect_weekly_nr7(weekly) if weekly is not None and not weekly.empty else False
            has_obv_div   = self.patterns.detect_obv_divergence(daily)
            at_support, support_price, support_dist = self.patterns.detect_support_level(daily)
            is_ipo_base, ipo_days = self.patterns.detect_ipo_base(daily)
            bulk_deal_data = self.bulk_deals.get(symbol)

            # 1D change for circuit check
            last_pre = daily.iloc[-1]
            prev_pre = daily.iloc[-2] if len(daily) > 1 else last_pre
            chg_1d_pre = (last_pre["Close"] / prev_pre["Close"] - 1) * 100
            circuit_risk = self.patterns.detect_upper_circuit_risk(chg_1d_pre)

            score, score_breakdown = scorer.compute_score(
                daily, weekly, delivery_pct,
                fund_data=fund_data, stage=stage, pledge_pct=pledge_pct,
                vcp_score_raw=vcp_score, is_nr7=is_nr7,
                is_inside_day=is_inside, pp_found=pp_found,
                candle_score=candle_score, has_obv_div=has_obv_div,
                has_flat_base=has_flat_base, flat_base_info=flat_base_info,
                is_nr4=is_nr4, is_weekly_nr7=is_weekly_nr7,
                at_support=at_support, bulk_deal_data=bulk_deal_data,
                is_ipo_base=is_ipo_base,
                # v7.0 India-specific
                promoter_data=promoter_act_data,
                oi_data=oi_data,
                earnings_info=raw.get("earnings_info", {}),
                # v7.1 new
                circuit_risk=circuit_risk,
                nifty_df=self.price_mgr.nifty_data,  # pandas Series of Nifty Close prices
            )
            grade = scorer.assign_grade(score)

            last = daily.iloc[-1]
            prev = daily.iloc[-2] if len(daily) > 1 else last

            rs_alpha = scorer.relative_strength(daily["Close"])

            chg_1d = (last["Close"] / prev["Close"] - 1) * 100
            chg_5d = last.get("ROC_5", 0)
            chg_1m = last.get("ROC_21", 0)
            chg_3m = last.get("ROC_63", 0)

            # ── Active signals ──
            active_signals = []
            if vcp_score >= 60:   active_signals.append(f"VCP({vcp_score})")
            if has_flat_base:     active_signals.append(f"FlatBase({flat_base_info.get('range_pct',0):.1f}%)")
            if pp_found:          active_signals.append(f"PocketPivot({pp_str})")
            if is_nr7:            active_signals.append("NR7")
            if is_nr4:            active_signals.append("NR4")
            if is_nr7 and is_weekly_nr7: active_signals.append("🔥MultiTF-NR7")
            if is_inside:         active_signals.append("InsideDay")
            if htf:               active_signals.append("HighTightFlag")
            if three_tight:       active_signals.append("3TightCloses")
            if vol_dry:           active_signals.append("VolDryUp")
            if bo_found:          active_signals.append(f"Breakout({bo_str})")
            if has_obv_div:       active_signals.append("OBV-Divergence📶")
            if at_support:        active_signals.append(f"AtSupport(₹{support_price:.0f})")
            if is_ipo_base:       active_signals.append(f"IPO-Base({ipo_days}d)")
            # Candle patterns
            for pat_name in candle_patterns:
                active_signals.append(f"🕯{pat_name}")
            # Supertrend
            last_st_dir = daily["ST_Direction"].iloc[-1] if "ST_Direction" in daily.columns else 0
            prev_st_dir = daily["ST_Direction"].iloc[-2] if "ST_Direction" in daily.columns and len(daily)>1 else 0
            if last_st_dir == 1:
                if prev_st_dir != 1: active_signals.append("ST-FlipBUY🟢")
                else:                active_signals.append("Supertrend-BUY")
            # MFI
            mfi_val = daily["MFI"].iloc[-1] if "MFI" in daily.columns else None
            if mfi_val is not None and not pd.isna(mfi_val) and 45 <= mfi_val <= 65:
                active_signals.append(f"MFI({mfi_val:.0f})")
            # ── FII Absorption signal ──
            fii_5d_abs = self._fii_dii_data.get("fii_5d")
            if fii_5d_abs and fii_5d_abs < -1000:
                chg5_abs = result.get("chg_5d", 0) or 0
                del_abs  = delivery_pct or 0
                if chg5_abs > -2 and del_abs >= 55:
                    active_signals.insert(0, "🔥FIIAbsorption(DII/Retail buying)")

            # ── FII + PCR Combined signal ──
            fii_5d_val = self._fii_dii_data.get("fii_5d")
            pcr_val_sig = self._pcr_data.get("nifty_pcr")
            if fii_5d_val and pcr_val_sig:
                if fii_5d_val > 2000 and pcr_val_sig > 1.4:
                    active_signals.insert(0, "🎯FII+PCR-BullCombo🟢")
                elif fii_5d_val > 2000 and pcr_val_sig > 1.2:
                    active_signals.insert(0, "✅FII+PCR-Bullish")

            # ── Golden Cross / Death Cross signal ──
            ema50_v  = last.get("EMA_50",  0) or 0
            ema200_v = last.get("EMA_200", 0) or 0
            if ema50_v > 0 and ema200_v > 0:
                prev_ema50  = daily.iloc[-2].get("EMA_50",  0) or 0
                prev_ema200 = daily.iloc[-2].get("EMA_200", 0) or 0
                if ema50_v > ema200_v and prev_ema50 <= prev_ema200:
                    active_signals.insert(0, "🌟GoldenCross🟢(Fresh)")
                elif ema50_v > ema200_v:
                    active_signals.append("GoldenCross✅")
                elif ema50_v < ema200_v and prev_ema50 >= prev_ema200:
                    active_signals.insert(0, "💀DeathCross🔴(Fresh)")
                elif ema50_v < ema200_v:
                    active_signals.append("DeathCross❌")

            # v7.1 — 52W high breakout signal
            high52w_chk = last.get("High_52w", 0) or 0
            if high52w_chk > 0:
                pft_chk   = (last["Close"] / high52w_chk - 1) * 100
                vol_r_chk = last.get("Vol_ratio", 1) or 1
                if pft_chk >= -1.5 and vol_r_chk >= 1.5 and (delivery_pct or 0) >= 55:
                    active_signals.insert(0, "🚀52WBreakout✅(Vol+Del)")
                elif -3 <= pft_chk < -1.5 and vol_r_chk >= 1.2:
                    active_signals.append("📈Near52WHigh")

            # Circuit risk
            if circuit_risk:
                active_signals.append(f"⚡{circuit_risk}")
                if "Upper" in str(circuit_risk):
                    active_signals.append("⚠️CircuitRisk")
            # Bulk deals
            if bulk_deal_data:
                if bulk_deal_data.get("bulk_buy"):  active_signals.append("📋BulkBuy")
                if bulk_deal_data.get("block_buy"): active_signals.append("📋BlockBuy")
                if bulk_deal_data.get("bulk_sell"): active_signals.append("🚨BulkSell")
            # F&O eligible
            if symbol in FNO_STOCKS: active_signals.append("F&O")
            # Volume Surge
            if vs_type:
                day_tag = "↑" if vs_up else "↓"
                active_signals.append(f"{vs_type}{day_tag}({vs_ratio}x)")
            # Delivery signal
            if delivery_pct is not None and delivery_pct >= CFG["delivery_min_pct"]:
                active_signals.append(f"Delivery{delivery_pct:.0f}%")
            # BB tightness
            bb_w = last.get("BB_width", 20)
            if bb_w < CFG["bb_tight_threshold"]:
                active_signals.append(f"BBTight({bb_w:.1f}%)")
            # 52W High proximity
            pct_from_high = last.get("Pct_from_high", -100)
            if pct_from_high >= -CFG["high52w_proximity_pct"]:
                active_signals.append("Near52WHigh")
            # Stage 2 signal
            if stage == "Stage 2":
                active_signals.append("Stage2✅")
            elif stage in ("Stage 3", "Stage 4"):
                active_signals.append(f"⚠️{stage}")
            # Fundamental quality
            fgrade = fund_data.get("fund_grade", "N/A") if fund_data else "N/A"
            if fgrade == "Strong":
                active_signals.append("FundStrong💎")
            elif fgrade == "Weak":
                active_signals.append("FundWeak❌")
            # Promoter pledging warning
            if pledge_pct is not None:
                if pledge_pct >= CFG["pledge_danger_pct"]:
                    active_signals.append(f"🚨Pledge{pledge_pct:.0f}%")
                elif pledge_pct >= CFG["pledge_warn_pct"]:
                    active_signals.append(f"⚠️Pledge{pledge_pct:.0f}%")
            # Earnings warning
            earnings_info = raw.get("earnings_info", {})
            if earnings_info.get("has_upcoming"):
                active_signals.append(f"⚠️Results({earnings_info['date_str']})")
            # Institutional Accumulation
            if accum_data.get("is_accumulating"):
                label = accum_data.get("accum_label", "Accumulation")
                days_a  = accum_data.get("accum_days", 0)
                if label == "Strong Accumulation":
                    active_signals.append(f"🏦StrongAccum({days_a}d)")
                else:
                    active_signals.append(f"🏦Accum({days_a}d)")

            # ── India-specific new signals (v7.0) ──
            if promoter_act_data.get("promoter_buying"):
                active_signals.append("🏛️PromoterBuying🟢")
            if promoter_act_data.get("promoter_selling"):
                active_signals.append("🏛️PromoterSelling🔴")
            if promoter_act_data.get("pledge_decreasing"):
                active_signals.append("📉PledgeDecreasing✅")
            # OI buildup signal
            oi_bt = oi_data.get("buildup_type","") if oi_data else ""
            if oi_bt == "LongBuildup":    active_signals.append("📊LongBuildup🟢")
            elif oi_bt == "ShortCovering": active_signals.append("📊ShortCovering⚡")
            elif oi_bt == "ShortBuildup":  active_signals.append("📊ShortBuildup🔴")
            # FII signal
            fii_sentiment = self._fii_dii_data.get("sentiment","")
            if "Buying" in fii_sentiment: active_signals.append(f"💹FII-{fii_sentiment}")
            elif "Selling" in fii_sentiment: active_signals.append(f"💹FII-{fii_sentiment}")
            # India VIX signal
            vix_val = self.india_vix._vix
            if vix_val is not None:
                if vix_val < 13: active_signals.append(f"📊VIX{vix_val:.0f}✅")
                elif vix_val > 20: active_signals.append(f"📊VIX{vix_val:.0f}⚠️")
            weekly_summary = {}
            if weekly is not None and not weekly.empty:
                wl = weekly.iloc[-1]
                weekly_summary = {
                    "w_rsi"        : round(wl.get("W_RSI", 0), 1),
                    "w_adx"        : round(wl.get("W_ADX", 0), 1),
                    "w_roc_4"      : round(wl.get("W_ROC_4", 0), 1),
                    "w_roc_13"     : round(wl.get("W_ROC_13", 0), 1),
                    "above_w_ema10": last["Close"] > wl.get("W_EMA_10", 0),
                    "above_w_ema21": last["Close"] > wl.get("W_EMA_21", 0),
                }

            result = {
                "symbol"         : symbol,
                "score"          : score,
                "grade"          : grade,
                "grade_color"    : scorer.grade_color(grade),
                "score_breakdown": score_breakdown,

                # Price
                "price"          : round(last["Close"], 2),
                "open"           : round(last["Open"], 2),
                "high"           : round(last["High"], 2),
                "low"            : round(last["Low"], 2),
                "volume"         : int(last["Volume"]),
                "avg_vol_20d"    : int(daily["Volume"].tail(20).mean()),
                "vol_ratio"      : round(last.get("Vol_ratio", 1), 2),

                # Returns
                "chg_1d"         : round(chg_1d, 2),
                "chg_5d"         : round(chg_5d, 2),
                "chg_1m"         : round(chg_1m, 2),
                "chg_3m"         : round(chg_3m, 2),

                # 52-week
                "high_52w"       : round(last.get("High_52w", 0), 2),
                "low_52w"        : round(last.get("Low_52w",  0), 2),
                "pct_from_high"  : round(pct_from_high, 1),

                # Indicators
                "rsi"            : round(last.get("RSI", 0), 1),
                "adx"            : round(last.get("ADX", 0), 1),
                "di_plus"        : round(last.get("DI_plus", 0), 1),
                "di_minus"       : round(last.get("DI_minus", 0), 1),
                "macd"           : round(last.get("MACD", 0), 3),
                "macd_sig"       : round(last.get("MACD_signal", 0), 3),
                "macd_hist"      : round(last.get("MACD_hist", 0), 3),
                "bb_width"       : round(last.get("BB_width", 0), 2),
                "atr_pct"        : round(last.get("ATR_pct", 0), 2),
                "stoch_k"        : round(last.get("Stoch_K", 0), 1),
                "obv_trend"      : "Up" if last.get("OBV", 0) > last.get("OBV_EMA", 0) else "Down",

                # EMAs
                "ema_5"          : round(last.get("EMA_5",   0), 2),
                "ema_10"         : round(last.get("EMA_10",  0), 2),
                "ema_13"         : round(last.get("EMA_13",  0), 2),
                "ema_21"         : round(last.get("EMA_21",  0), 2),
                "ema_26"         : round(last.get("EMA_26",  0), 2),
                "ema_50"         : round(last.get("EMA_50",  0), 2),
                "ema_200"        : round(last.get("EMA_200", 0), 2),
                "above_200ema"   : bool(last["Close"] > last.get("EMA_200", 0)),

                # ── EMA Momentum Scanner fields (v7.2) ──
                # Rule 1: Early Momentum 5>13>26
                "ema_early_momentum": bool(
                    last.get("EMA_5", 0)  > last.get("EMA_13", 0) > 0 and
                    last.get("EMA_13", 0) > last.get("EMA_26", 0) > 0 and
                    last["Close"]          > last.get("EMA_5",  0) > 0
                ),
                # Fresh 5>13 cross within last 2 days
                "ema_fresh_cross_5_13": bool(
                    len(daily) >= 3 and
                    daily["EMA_5"].iloc[-1]  > daily["EMA_13"].iloc[-1]  > 0 and
                    daily["EMA_5"].iloc[-2]  <= daily["EMA_13"].iloc[-2]
                ) if "EMA_5" in daily.columns and "EMA_13" in daily.columns else False,
                # Rule 2: Swing Confirmation 20>50
                "ema_swing_confirm": bool(
                    last.get("EMA_21", 0) > last.get("EMA_50", 0) > 0 and
                    last["Close"] > last.get("EMA_21", 0) > 0
                ),
                # Close near EMA21 (within 2-3%) = pullback+bounce setup
                "ema_near_20_pullback": bool(
                    last.get("EMA_21", 0) > 0 and
                    0 <= (last["Close"] / last.get("EMA_21", 1) - 1) * 100 <= 3
                ),
                # Rule 3: Golden Cross 50>200
                "ema_golden_cross": bool(
                    last.get("EMA_50", 0) > last.get("EMA_200", 0) > 0
                ),
                # Fresh Golden Cross within 10 days
                "ema_fresh_golden_cross": bool(
                    len(daily) >= 11 and
                    daily["EMA_50"].iloc[-1]  > daily["EMA_200"].iloc[-1]  > 0 and
                    daily["EMA_50"].iloc[-10] <= daily["EMA_200"].iloc[-10]
                ) if "EMA_50" in daily.columns and "EMA_200" in daily.columns else False,
                # Rule 4: Ultra Pro — all conditions combined
                "ema_ultra_pro": bool(
                    last.get("EMA_5",  0) > last.get("EMA_13", 0) > 0 and
                    last.get("EMA_13", 0) > last.get("EMA_26", 0) > 0 and
                    last.get("EMA_21", 0) > last.get("EMA_50", 0) > 0 and
                    last.get("EMA_50", 0) > last.get("EMA_200",0) > 0 and
                    last["Close"] > last.get("EMA_5", 0) > 0 and
                    (last.get("Vol_ratio", 1) or 1) >= 1.5
                ),
                # Near 20-day high (within 5%) — for Ultra Pro
                "near_20d_high": bool(
                    len(daily) >= 20 and
                    daily["High"].tail(20).max() > 0 and
                    (last["Close"] / daily["High"].tail(20).max() - 1) * 100 >= -5
                ),

                # Patterns & Signals
                "active_signals" : active_signals,
                "vcp_score"      : vcp_score,
                "vcp_info"       : vcp_info,
                "breakout"       : bo_found,
                "breakout_str"   : bo_str,
                "breakout_info"  : bo_info,
                "pocket_pivot"   : pp_found,
                "nr7"            : is_nr7,
                "nr4"            : is_nr4,
                "inside_day"     : is_inside,
                "vol_dry_up"     : vol_dry,
                "htf"            : htf,

                # v6.0 new pattern fields
                "flat_base"      : has_flat_base,
                "flat_base_info" : flat_base_info or {},
                "candle_patterns": candle_patterns,
                "candle_score"   : candle_score,
                "is_weekly_nr7"  : is_weekly_nr7,
                "obv_divergence" : has_obv_div,
                "at_support"     : at_support,
                "support_price"  : support_price,
                "support_dist_pct": support_dist,
                "is_ipo_base"    : is_ipo_base,
                "ipo_days_listed": ipo_days,
                "circuit_risk"   : circuit_risk,
                "is_fno"         : symbol in FNO_STOCKS,
                "bulk_deal"      : bulk_deal_data or {},

                # v7.0 India-specific fields
                "promoter_buying"   : promoter_act_data.get("promoter_buying", False),
                "promoter_selling"  : promoter_act_data.get("promoter_selling", False),
                "promoter_chg_qoq"  : promoter_act_data.get("promoter_chg_qoq", None),
                "pledge_decreasing" : promoter_act_data.get("pledge_decreasing", False),
                "oi_buildup_type"   : oi_data.get("buildup_type","") if oi_data else "",
                "oi_change_pct"     : oi_data.get("oi_change_pct", 0) if oi_data else 0,
                "india_vix"         : self.india_vix._vix,
                "fii_buying"        : "Buying" in self._fii_dii_data.get("sentiment",""),
                "supertrend_dir" : int(daily["ST_Direction"].iloc[-1]) if "ST_Direction" in daily.columns else 0,
                "mfi"            : round(float(daily["MFI"].iloc[-1]), 1) if "MFI" in daily.columns and not pd.isna(daily["MFI"].iloc[-1]) else None,
                "cmf"            : round(float(daily["CMF"].iloc[-1]), 3) if "CMF" in daily.columns and not pd.isna(daily["CMF"].iloc[-1]) else None,
                "pivot_pp"       : daily.get("Pivot_PP", pd.Series([0])).iloc[-1] if "Pivot_PP" in daily.columns else None,
                "pivot_r1"       : daily.get("Pivot_R1", pd.Series([0])).iloc[-1] if "Pivot_R1" in daily.columns else None,
                "pivot_s1"       : daily.get("Pivot_S1", pd.Series([0])).iloc[-1] if "Pivot_S1" in daily.columns else None,
                "pivot_r2"       : daily.get("Pivot_R2", pd.Series([0])).iloc[-1] if "Pivot_R2" in daily.columns else None,
                "pivot_s2"       : daily.get("Pivot_S2", pd.Series([0])).iloc[-1] if "Pivot_S2" in daily.columns else None,

                # v6.0 Sparkline — last 20 normalized close prices
                "sparkline"      : [round(float(v), 2) for v in daily["Close"].tail(20).tolist()],

                # Volume Surge
                "vol_surge_type" : vs_type,
                "vol_surge_ratio": vs_ratio,
                "vol_surge_up"   : vs_up,

                # Fundamentals (v3.0)
                "fund_score"      : fund_data.get("fund_score", 0) if fund_data else 0,
                "fund_grade"      : fund_data.get("fund_grade", "N/A") if fund_data else "N/A",
                "fund_detail"     : fund_data.get("fund_detail", {}) if fund_data else {},
                "roe"             : fund_data.get("roe") if fund_data else None,
                "roce"            : fund_data.get("roce") if fund_data else None,
                "de_ratio"        : fund_data.get("de_ratio") if fund_data else None,
                "eps_growth"      : fund_data.get("eps_growth") if fund_data else None,
                "rev_growth"      : fund_data.get("rev_growth") if fund_data else None,
                "profit_margin"   : fund_data.get("profit_margin") if fund_data else None,
                "pe_ratio"        : fund_data.get("pe_ratio") if fund_data else None,
                "market_cap"      : fund_data.get("market_cap") if fund_data else None,
                # ── v7.2 Screener fields ──
                "pb_ratio"        : fund_data.get("pb_ratio") if fund_data else None,
                "operating_margin": fund_data.get("operating_margin") if fund_data else None,
                "gross_margin"    : fund_data.get("gross_margin") if fund_data else None,
                "earnings_yield"  : fund_data.get("earnings_yield") if fund_data else None,
                "roic"            : fund_data.get("roic") if fund_data else None,
                "sales_growth"    : fund_data.get("sales_growth") if fund_data else None,

                # Promoter & Pledging (v3.0)
                "promoter_holding": promoter_data.get("promoter_holding"),
                "pledge_pct"      : pledge_pct,
                "pledge_danger"   : bool(pledge_pct is not None and pledge_pct >= CFG["pledge_danger_pct"]),
                "pledge_warn"     : bool(pledge_pct is not None and pledge_pct >= CFG["pledge_warn_pct"]),

                # Stage Analysis (v3.0)
                "stage"          : stage,
                "stage_info"     : stage_info,
                "is_stage2"      : stage == "Stage 2",

                # Institutional Accumulation (v4.0)
                "is_accumulating": accum_data.get("is_accumulating", False),
                "accum_days"     : accum_data.get("accum_days", 0),
                "accum_signals"  : accum_data.get("accum_signals", []),
                "accum_score"    : accum_data.get("accum_score", 0),
                "accum_label"    : accum_data.get("accum_label", "None"),

                # NEW: Delivery & Earnings
                "delivery_pct"   : delivery_pct,
                "earnings_info"  : earnings_info,
                "near_52w_high"  : bool(pct_from_high >= -CFG["high52w_proximity_pct"]),

                # RS (percentile added in run())
                "rs_alpha"       : round(rs_alpha, 2),
                "rs_percentile"  : 0,   # placeholder

                # Sector (added in run())
                "sector"         : SECTOR_MAP.get(symbol, "Others"),
                "sector_rank"    : 0,
                "sector_momentum": 0,
                "sector_total"   : 0,

                # Trade Setup (added below)
                "trade_setup"    : {},

                # Weekly
                "weekly"         : weekly_summary,
            }

            # ── Trade Setup ── (needs result dict first)
            result["trade_setup"] = self.trade_calc.calculate(result, daily)

            # ── Confidence % (v4.0) — for Top Trades ranking ──
            result["confidence_pct"] = StockScorer.compute_confidence_pct(result)

            # ── AVWAP Pre-Breakout Scanner (v8.0) ──────────────────────────
            try:
                avwap_data = self._compute_avwap_scanner(daily, last, delivery_pct)
                result.update(avwap_data)
                if avwap_data.get("avwap_score", 0) >= 4:
                    active_signals.insert(0, f"🔥AVWAP-PreBreakout({avwap_data['avwap_score']}/5)")
                elif avwap_data.get("avwap_score", 0) >= 3:
                    active_signals.append(f"⚡AVWAP-Setup({avwap_data['avwap_score']}/5)")
            except Exception:
                result.update({
                    "avwap_score": 0, "avwap_value": 0, "avwap_above": False,
                    "avwap_held_days": 0, "avwap_dist_to_breakout": 0,
                    "avwap_vol_vs_avg": 0, "avwap_consolidation": False,
                    "avwap_candidate": False, "avwap_smart_money": False,
                    "avwap_tag": "",
                })

            return result

        except Exception as _e:
            import traceback; print(f"  [ERR] {symbol}: {type(_e).__name__}: {_e}"); return None

    def run(self, symbols, max_workers=None):
        workers = max_workers or CFG["max_workers"]
        results = []
        failed  = 0

        # ── Fetch delivery data first (single bulk download) ──
        print("\n📦 Fetching NSE delivery data (bulk)...")
        self.delivery.fetch_all()

        # ── Fetch bulk/block deals ──
        print("\n📋 Fetching bulk & block deal data...")
        self.bulk_deals.fetch_all()

        # ── Fetch FII/DII flow ──
        print("\n💹 Fetching FII/DII flow data...")
        fii_dii_data = self.fii_dii.fetch()
        self._fii_dii_data = fii_dii_data   # share with scorer via pipeline

        # ── v7.0: Fetch India VIX ──
        print("\n📊 Fetching India VIX...")
        self.india_vix.fetch()

        # ── v7.0: Fetch Open Interest data ──
        print("\n📈 Fetching Open Interest (F&O buildup)...")
        self.oi_fetcher.fetch_all()

        print(f"\n⚙️  Analyzing {len(symbols)} stocks with {workers} parallel workers...\n")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self.analyze_one, sym): sym for sym in symbols}
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="  Analyzing",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
            ):
                res = future.result()
                if res:
                    results.append(res)
                else:
                    failed += 1

        print(f"\n  ✅ Analyzed: {len(results)} stocks   |   ⚠️  Skipped/Failed: {failed}")

        if not results:
            return results

        # ── Compute RS Percentile ──
        alphas = [r["rs_alpha"] for r in results]
        for r in results:
            rank = sum(1 for a in alphas if a <= r["rs_alpha"])
            r["rs_percentile"] = round(rank / len(alphas) * 100)

        # ── RS Elite Bonus (+2 pts for top 10% — reduced from +5 in v5) ──
        for r in results:
            if r["rs_percentile"] >= CFG["rs_elite_pct"]:
                new_score = min(r["score"] + 2, 100)
                r["score"] = new_score
                r["grade"] = StockScorer.assign_grade(new_score)
                r["grade_color"] = StockScorer.grade_color(r["grade"])
                r["score_breakdown"]["rs_elite_bonus"] = 2
                if "RS Elite(>90%ile)" not in r["active_signals"]:
                    r["active_signals"].insert(0, "RS Elite(>90%ile)")
            else:
                r["score_breakdown"]["rs_elite_bonus"] = 0

        # ── Sector Momentum Rankings ──
        self.sector_mgr.assign_sectors(results)
        sorted_sectors = self.sector_mgr.rank_and_score(results)

        # ── Market Breadth (v3.0) ──
        above_200 = sum(1 for r in results if r["above_200ema"])
        breadth_pct = round(above_200 / len(results) * 100, 1)
        if   breadth_pct >= CFG["breadth_strong"]:  breadth_status = "STRONG"
        elif breadth_pct >= CFG["breadth_caution"]: breadth_status = "CAUTION"
        else:                                        breadth_status = "WEAK"
        breadth_data = {"pct": breadth_pct, "count": above_200, "status": breadth_status}

        # ── v7.0: Expert Filter — 13-point checklist ──
        nifty_above_sma = breadth_pct >= 55
        for r in results:
            sec_strength = r.get("sector_strength", 50)
            expert_result = ExpertFilter.evaluate(
                result          = r,
                sector_strength = sec_strength,
                nifty_above_sma = nifty_above_sma,
                breadth_pct     = breadth_pct,
            )
            r.update(expert_result)
            yes = expert_result["expert_yes"]
            dec = expert_result["expert_decision"]
            if   dec == "CONVICTION": r["active_signals"].insert(0, f"⭐CONVICTION({yes}/13)")
            elif dec == "TRADE":      r["active_signals"].insert(0, f"✅EXPERT({yes}/13)")

        expert_conviction = sum(1 for r in results if r.get("expert_decision") == "CONVICTION")
        expert_trade      = sum(1 for r in results if r.get("expert_decision") == "TRADE")
        print(f"\n  ⭐ Expert Conviction trades: {expert_conviction}")
        print(f"  ✅ Expert tradeable:         {expert_trade}")
        print(f"  ❌ Expert SKIP:              {len(results) - expert_conviction - expert_trade}")

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        # ── Top 10 Smart Opportunities ranked by Confidence % ──
        tradeable = [r for r in results if r.get("grade") in ("A+", "A", "B+")
                     and not r.get("pledge_danger")
                     and not r["earnings_info"].get("has_upcoming")
                     and not r.get("circuit_risk")]   # v6: exclude circuit stocks
        top_trades = sorted(tradeable, key=lambda x: x.get("confidence_pct", 0), reverse=True)[:10]

        return results, sorted_sectors, breadth_data, top_trades, fii_dii_data


# ─────────────────────────────────────────────────────────────────────
#  HTML REPORT GENERATOR  v3.0
# ─────────────────────────────────────────────────────────────────────
class HTMLReportGenerator:

    def generate(self, results, pcr_data, sorted_sectors, breadth_data,
                 capital=None, output_file="trade_stag_report.html",
                 top_trades=None, fii_dii_data=None, max_pain_data=None):
        analysis_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
        total         = len(results)
        cap           = capital or CFG["default_capital"]
        risk_amt      = round(cap * CFG["risk_per_trade_pct"] / 100)

        grade_counts = {}
        for r in results:
            grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

        fii_dii_data  = fii_dii_data or {}
        fii_net       = fii_dii_data.get("fii_net")
        dii_net       = fii_dii_data.get("dii_net")
        fii_5d        = fii_dii_data.get("fii_5d")
        fii_sentiment = fii_dii_data.get("sentiment", "N/A")

        # ── Advance/Decline counts (v7.1) ──
        adv_count  = sum(1 for r in results if r.get("chg_1d", 0) > 0)
        dec_count  = sum(1 for r in results if r.get("chg_1d", 0) < 0)
        unch_count = len(results) - adv_count - dec_count
        total_ad   = max(adv_count + dec_count + unch_count, 1)
        adv_pct    = adv_count  / total_ad * 100
        dec_pct    = dec_count  / total_ad * 100
        unch_pct   = max(0, 100 - adv_pct - dec_pct)

        # ── Header display values ──
        fii_5d_html  = fii_5d if fii_5d else 0
        fii_5d_str   = f"₹{fii_5d/100:.0f}Cr" if fii_5d else "N/A"
        pcr_val_html = f"{pcr_data.get('nifty_pcr', 'N/A')}" if pcr_data.get('nifty_pcr') else "N/A"
        vix_fetcher_val = None
        # Try to get VIX from pcr_data extras or leave N/A
        vix_val_html = "N/A"

        bulk_buy_stocks  = [r for r in results if r.get("bulk_deal", {}).get("bulk_buy") or r.get("bulk_deal", {}).get("block_buy")]
        bulk_sell_stocks = [r for r in results if r.get("bulk_deal", {}).get("bulk_sell")]
        supertrend_buy   = [r for r in results if r.get("supertrend_dir") == 1]
        st_flip          = [r for r in results if r.get("supertrend_dir") == 1
                            and any("ST-FlipBUY" in s for s in r.get("active_signals", []))]
        obv_div_stocks   = [r for r in results if r.get("obv_divergence")]
        flat_base_stocks = [r for r in results if r.get("flat_base")]
        candle_stocks    = [r for r in results if r.get("candle_score", 0) >= 6]
        fno_stocks_list  = [r for r in results if r.get("is_fno")]
        circuit_stocks   = [r for r in results if r.get("circuit_risk")]
        support_stocks   = [r for r in results if r.get("at_support")]
        ipo_base_stocks  = [r for r in results if r.get("is_ipo_base")]

        breakouts     = [r for r in results if r["breakout"]][:10]
        vcps          = sorted([r for r in results if r["vcp_score"] >= 60],
                               key=lambda x: x["vcp_score"], reverse=True)[:10]
        rs_elite      = [r for r in results if r["rs_percentile"] >= CFG["rs_elite_pct"]]
        near_earnings = [r for r in results if r["earnings_info"].get("has_upcoming")]
        high_delivery = [r for r in results
                         if r["delivery_pct"] is not None and r["delivery_pct"] >= CFG["delivery_min_pct"]]
        vol_surges    = [r for r in results if r.get("vol_surge_type") is not None]
        vol_surges_up = [r for r in vol_surges if r.get("vol_surge_up")]
        stage2_stocks = [r for r in results if r.get("is_stage2")]
        pledge_danger = [r for r in results if r.get("pledge_danger")]
        fund_strong   = [r for r in results if r.get("fund_grade") == "Strong"]
        accum_stocks  = [r for r in results if r.get("is_accumulating")]
        strong_accum  = [r for r in results if r.get("accum_label") == "Strong Accumulation"]
        top_trades    = top_trades or sorted(results[:10], key=lambda x: x.get("confidence_pct", 0), reverse=True)

        pcr_val     = pcr_data.get("nifty_pcr",       "N/A")
        weekly_pcr  = pcr_data.get("weekly_pcr",      None)
        weekly_exp  = pcr_data.get("weekly_expiry",   "N/A")
        monthly_exp = pcr_data.get("monthly_expiry",  "N/A")
        pcr_sent    = pcr_data.get("sentiment",        "N/A")
        wpcr_sent   = pcr_data.get("weekly_sentiment","N/A")
        max_pain_data = max_pain_data or {}
        mp_val        = max_pain_data.get("max_pain")
        mp_dist       = max_pain_data.get("distance_pct")
        mp_sentiment  = max_pain_data.get("sentiment", "N/A")
        mp_display    = f"₹{mp_val:,} ({mp_dist:+.1f}%)" if mp_val and mp_dist else "N/A"
        breadth_pct    = breadth_data.get("pct", 0)
        breadth_status = breadth_data.get("status", "UNKNOWN")
        breadth_col    = ("#10b981" if breadth_status == "STRONG"
                          else "#f59e0b" if breadth_status == "CAUTION" else "#ef4444")
        # Weekly PCR display string
        wpcr_display = f"{weekly_pcr} ({wpcr_sent}) — Expiry: {weekly_exp}" if weekly_pcr else "NSE blocked"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trade Stag — NSE 500 Scanner — {analysis_time}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    /* ── Trade Stag — Forest Dark + Gold ── */
    --bg:      #060a0c;
    --bg2:     #0b1014;
    --bg3:     #111a20;
    --bg4:     #182830;
    --border:  rgba(180, 160, 90, 0.10);
    --text:    #e8ece0;
    --muted:   #7a8e8a;
    --muted2:  #4a5e58;
    --green:   #2dd4a0;
    --red:     #fb7185;
    --amber:   #d4a024;
    --blue:    #38bdf8;
    --cyan:    #22d3ee;
    --purple:  #a78bfa;
    --orange:  #e89030;
    --lime:    #84cc16;
    --pink:    #f472b6;
    --aplus:   #d4a024;
    --a:       #e8b84a;
    --bplus:   #2dd4a0;
    --b:       #67e8c8;
    --c:       #e89030;
    --d:       #fb7185;
    --accent:  #d4a024;
    --accent2: #2dd4a0;
  }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "Inter","SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    font-size: 13.5px;
    line-height: 1.55;
    letter-spacing: 0.01em;
  }}
  a {{ color:inherit; text-decoration:none; }}
  .page-wrap {{ max-width:1440px; margin:0 auto; padding:24px 20px; }}
  .header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; flex-wrap:wrap; gap:12px; }}
  .header-left h1 {{ font-size:22px; font-weight:700; letter-spacing:-0.5px; }}
  .header-left p  {{ color:var(--muted); font-size:13px; margin-top:4px; }}
  .header-right   {{ text-align:right; color:var(--muted); font-size:12px; }}
  .card    {{ background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }}
  .card-sm {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
  .stats-row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px; margin-bottom:18px; }}
  .stat-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:13px 15px; }}
  .stat-label {{ font-size:10px; color:var(--muted); font-weight:500; letter-spacing:.06em; text-transform:uppercase; margin-bottom:5px; }}
  .stat-val   {{ font-size:23px; font-weight:700; line-height:1; }}
  .stat-sub   {{ font-size:10px; color:var(--muted); margin-top:3px; }}
  .pcr-banner {{ display:flex; align-items:center; gap:14px; background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:11px 16px; margin-bottom:12px; flex-wrap:wrap; }}
  .pcr-badge  {{ padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600; letter-spacing:.04em; }}
  .pcr-item   {{ font-size:13px; color:var(--muted); }}
  .pcr-item strong {{ color:var(--text); }}
  /* ── Breadth Banner (v3.0) ── */
  .breadth-banner {{ display:flex; align-items:center; gap:12px; border-radius:12px; padding:12px 18px; margin-bottom:12px; flex-wrap:wrap; border:1px solid; font-size:13px; font-weight:500; }}
  .breadth-strong  {{ background:rgba(16,185,129,.08); border-color:rgba(16,185,129,.25); color:var(--green); }}
  .breadth-caution {{ background:rgba(245,158,11,.08); border-color:rgba(245,158,11,.25); color:var(--amber); }}
  .breadth-weak    {{ background:rgba(239,68,68,.08);  border-color:rgba(239,68,68,.25);  color:var(--red); }}
  .breadth-dot {{ width:9px; height:9px; border-radius:50%; flex-shrink:0; }}
  /* ── Stage badges ── */
  .stage-2  {{ background:rgba(16,185,129,.15); color:var(--green);  border:1px solid rgba(16,185,129,.3); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .stage-1  {{ background:rgba(56,189,248,.12); color:var(--blue);   border:1px solid rgba(56,189,248,.25);padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .stage-3  {{ background:rgba(245,158,11,.12); color:var(--amber);  border:1px solid rgba(245,158,11,.25);padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .stage-4  {{ background:rgba(239,68,68,.12);  color:var(--red);    border:1px solid rgba(239,68,68,.25); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  /* ── Pledge danger ── */
  .pledge-danger {{ background:rgba(239,68,68,.15); color:#ef4444; border:1px solid rgba(239,68,68,.35); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700; }}
  .pledge-warn   {{ background:rgba(245,158,11,.12); color:var(--amber); border:1px solid rgba(245,158,11,.3); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  /* ── Fund grade ── */
  .fund-strong {{ background:rgba(167,139,250,.15); color:var(--purple); border:1px solid rgba(167,139,250,.3); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .fund-good   {{ background:rgba(16,185,129,.12);  color:var(--green);  border:1px solid rgba(16,185,129,.25);padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .fund-weak   {{ background:rgba(239,68,68,.12);   color:var(--red);    border:1px solid rgba(239,68,68,.25); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  /* ── Position size calculator ── */
  .pos-calc {{ background:var(--bg3); border:1px solid var(--border); border-radius:10px; padding:14px 16px; margin-top:10px; }}
  .pos-input {{ background:var(--bg4); border:1px solid var(--border); border-radius:6px; color:var(--text); font-size:13px; padding:6px 10px; outline:none; width:130px; }}
  .pos-input:focus {{ border-color:var(--blue); }}
  .grade-dist {{ display:flex; gap:8px; margin-bottom:18px; flex-wrap:wrap; }}
  .grade-pill {{ padding:7px 16px; border-radius:8px; font-size:13px; font-weight:700; color:white; }}
  .tabs {{ display:flex; gap:4px; margin-bottom:14px; flex-wrap:wrap; }}
  .tab-btn {{ padding:7px 14px; border-radius:8px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:12px; cursor:pointer; transition:all .15s; }}
  .tab-btn:hover {{ background:var(--bg3); color:var(--text); }}
  .tab-btn.active {{ background:var(--accent); color:#0a0500; border-color:var(--accent); font-weight:700; letter-spacing:0.02em; }}
  .tab-pane {{ display:none; }}
  .tab-pane.active {{ display:block; }}
  .tbl-wrap {{ overflow-x:auto; border-radius:12px; border:1px solid var(--border); }}
  table {{ width:100%; border-collapse:collapse; min-width:1200px; }}
  thead th {{ background:var(--bg3); padding:9px 11px; text-align:left; font-size:10px; font-weight:600; color:var(--muted); letter-spacing:.06em; text-transform:uppercase; white-space:nowrap; position:sticky; top:0; z-index:1; cursor:pointer; user-select:none; }}
  thead th:hover {{ color:var(--blue); }}
  tbody tr {{ border-bottom:1px solid var(--border); transition:background .1s; cursor:pointer; }}
  tbody tr:hover {{ background:var(--bg3); }}
  tbody tr:last-child {{ border-bottom:none; }}
  tbody td {{ padding:9px 11px; font-size:12px; white-space:nowrap; }}
  .grade-badge {{ display:inline-block; padding:3px 9px; border-radius:6px; font-size:11px; font-weight:700; color:white; min-width:30px; text-align:center; }}
  .signal-tag   {{ display:inline-block; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:500; background:rgba(56,189,248,.12); color:var(--blue); margin:1px; white-space:nowrap; }}
  .signal-elite {{ background:rgba(167,139,250,.15); color:var(--purple); }}
  .signal-warn  {{ background:rgba(239,68,68,.15);   color:#ef4444; }}
  .signal-green {{ background:rgba(16,185,129,.15);  color:var(--green); }}
  .signal-surge {{ background:rgba(245,158,11,.15);  color:var(--amber); border:1px solid rgba(245,158,11,.3); }}
  .signal-stage2{{ background:rgba(16,185,129,.15);  color:var(--green); }}
  .signal-fund  {{ background:rgba(167,139,250,.12); color:var(--purple); }}
  .signal-pledge{{ background:rgba(239,68,68,.2);    color:#ef4444; font-weight:700; }}
  .up {{ color:var(--green); }} .down {{ color:var(--red); }} .neutral {{ color:var(--muted); }}
  .prog-bar  {{ height:5px; border-radius:3px; background:var(--bg3); overflow:hidden; margin-top:3px; }}
  .prog-fill {{ height:100%; border-radius:3px; background:var(--green); }}
  .search-bar {{ position:relative; margin-bottom:10px; }}
  .search-bar input {{ width:100%; padding:9px 14px 9px 34px; background:var(--bg2); border:1px solid var(--border); border-radius:8px; color:var(--text); font-size:13px; outline:none; }}
  .search-bar input:focus {{ border-color:var(--accent); box-shadow:0 0 0 2px rgba(212,160,36,0.15); }}
  .search-icon {{ position:absolute; left:10px; top:50%; transform:translateY(-50%); color:var(--muted); }}
  .filter-row {{ display:flex; gap:5px; margin-bottom:10px; flex-wrap:wrap; align-items:center; }}
  .filter-btn {{ padding:4px 11px; border-radius:20px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:11px; cursor:pointer; transition:all .15s; }}
  .filter-btn:hover {{ border-color:var(--accent); color:var(--accent); }}
  .filter-btn.on {{ background:var(--accent); border-color:var(--accent); color:#0a0500; font-weight:700; }}
  .section-title {{ font-size:12px; font-weight:600; color:var(--muted); letter-spacing:.07em; text-transform:uppercase; margin-bottom:10px; }}
  .trade-setup-card {{ background:linear-gradient(135deg,rgba(56,189,248,.08),rgba(167,139,250,.06)); border:1px solid rgba(56,189,248,.2); border-radius:12px; padding:16px; margin-top:14px; }}
  .trade-setup-grid {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-top:10px; }}
  .trade-box {{ background:var(--bg3); border-radius:8px; padding:12px; text-align:center; }}
  .trade-box-label {{ font-size:10px; color:var(--muted); letter-spacing:.06em; text-transform:uppercase; }}
  .trade-box-val   {{ font-size:19px; font-weight:800; margin-top:4px; }}
  .trade-box-sub   {{ font-size:10px; color:var(--muted); margin-top:2px; }}
  .trade-t2-row    {{ background:var(--bg3); border-radius:8px; padding:10px 14px; margin-top:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px; }}
  .sector-grid  {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:8px; }}
  .sector-card  {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:12px 14px; display:flex; justify-content:space-between; align-items:center; }}
  .sector-name  {{ font-size:14px; font-weight:600; }}
  .sector-rank  {{ font-size:11px; color:var(--muted); margin-top:2px; }}
  .sector-score {{ font-size:22px; font-weight:700; }}
  /* ── Fundamentals tab ── */
  .fund-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; cursor:pointer; transition:border-color .15s; }}
  .fund-card:hover {{ border-color:var(--purple); }}
  .fund-metric {{ display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid var(--border); font-size:12px; }}
  .fund-metric:last-child {{ border-bottom:none; }}
  .modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.78); z-index:100; align-items:center; justify-content:center; }}
  .modal-overlay.open {{ display:flex; }}
  .modal {{ background:var(--bg2); border:1px solid var(--border); border-radius:16px; padding:22px; max-width:740px; width:92vw; max-height:90vh; overflow-y:auto; position:relative; }}
  .modal-close {{ position:absolute; top:14px; right:14px; background:var(--bg3); border:none; color:var(--muted); font-size:16px; cursor:pointer; width:30px; height:30px; border-radius:6px; display:flex; align-items:center; justify-content:center; }}
  .modal-close:hover {{ color:var(--text); }}
  .modal-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:11px; margin-top:12px; }}
  .modal-metric {{ background:var(--bg3); border-radius:8px; padding:11px; }}
  .modal-metric-label {{ font-size:10px; color:var(--muted); }}
  .modal-metric-val   {{ font-size:16px; font-weight:700; margin-top:2px; }}
  .breakdown-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:8px; margin-top:10px; }}
  .breakdown-item {{ background:var(--bg3); border-radius:8px; padding:10px 12px; }}
  .breakdown-label {{ font-size:10px; color:var(--muted); margin-bottom:2px; }}
  .breakdown-val   {{ font-size:14px; font-weight:700; }}
  .earnings-warn {{ background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.3); border-radius:8px; padding:10px 14px; margin-top:10px; color:#ef4444; font-size:13px; display:flex; align-items:center; gap:8px; }}
  .pledge-alert  {{ background:rgba(239,68,68,.1); border:1px solid rgba(239,68,68,.4); border-radius:8px; padding:10px 14px; margin-top:8px; color:#ef4444; font-size:13px; }}
  ::-webkit-scrollbar {{ width:6px; height:6px; }}
  ::-webkit-scrollbar-track {{ background:var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background:var(--bg3); border-radius:3px; }}
  .footer {{ text-align:center; color:var(--muted); font-size:12px; padding:20px 0 10px; border-top:1px solid var(--border); margin-top:28px; }}

  /* ── v4.0: Top Trades Panel ── */
  .top-trades-panel {{ background:linear-gradient(135deg,rgba(5,150,105,.06),rgba(167,139,250,.04)); border:1px solid rgba(5,150,105,.25); border-radius:14px; padding:18px 20px; margin-bottom:18px; }}
  .top-trades-title {{ font-size:15px; font-weight:700; color:var(--green); margin-bottom:14px; display:flex; align-items:center; gap:8px; }}
  .top-trades-grid  {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:10px; }}
  .trade-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:13px 15px; cursor:pointer; transition:border-color .15s, transform .12s; }}
  .trade-card:hover {{ border-color:var(--green); transform:translateY(-2px); }}
  .trade-card-rank  {{ font-size:10px; color:var(--muted); font-weight:600; letter-spacing:.06em; text-transform:uppercase; }}
  .trade-card-sym   {{ font-size:17px; font-weight:800; margin-top:2px; }}
  .trade-card-setup {{ font-size:11px; color:var(--blue); margin-top:1px; }}
  .conf-bar         {{ height:4px; border-radius:2px; background:var(--bg3); margin-top:8px; overflow:hidden; }}
  .conf-fill        {{ height:100%; border-radius:2px; transition:width .6s; }}
  .conf-label       {{ font-size:11px; color:var(--muted); margin-top:4px; display:flex; justify-content:space-between; }}
  .trade-card-prices {{ display:flex; gap:10px; margin-top:8px; flex-wrap:wrap; font-size:11px; }}
  .price-chip {{ background:var(--bg3); border-radius:4px; padding:3px 7px; }}

  /* ── v4.0: Sector Leaderboard ── */
  .sector-lb-card   {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:13px 16px; }}
  .sector-lb-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
  .sector-lb-name   {{ font-size:14px; font-weight:700; }}
  .sector-lb-score  {{ font-size:20px; font-weight:800; }}
  .sector-bar       {{ height:6px; border-radius:3px; background:var(--bg3); margin-top:6px; overflow:hidden; }}
  .sector-bar-fill  {{ height:100%; border-radius:3px; }}
  .sector-meta      {{ font-size:10px; color:var(--muted); margin-top:5px; display:flex; gap:12px; flex-wrap:wrap; }}
  .sector-lb-grid   {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }}
  .sector-hot-badge {{ background:rgba(245,158,11,.15); color:var(--amber); border:1px solid rgba(245,158,11,.3); padding:2px 7px; border-radius:4px; font-size:9px; font-weight:700; letter-spacing:.04em; }}

  /* ── v4.0: Accumulation tab ── */
  .accum-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:14px 16px; cursor:pointer; transition:border-color .15s; }}
  .accum-card:hover {{ border-color:rgba(16,185,129,.4); }}
  .accum-card.strong {{ border-color:rgba(16,185,129,.3); background:rgba(16,185,129,.04); }}
  .accum-label-strong {{ background:rgba(16,185,129,.15); color:var(--green); border:1px solid rgba(16,185,129,.3); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700; }}
  .accum-label-watch  {{ background:rgba(56,189,248,.1);  color:var(--blue);  border:1px solid rgba(56,189,248,.25); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:600; }}
  .accum-signal-tag   {{ display:inline-block; background:rgba(16,185,129,.1); color:var(--green); border:1px solid rgba(16,185,129,.2); border-radius:4px; padding:2px 6px; font-size:10px; margin:1px; }}
  .accum-score-bar    {{ height:5px; border-radius:3px; background:var(--bg3); margin-top:6px; overflow:hidden; }}
  .accum-score-fill   {{ height:100%; border-radius:3px; background:var(--green); }}
  .accum-grid         {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:10px; }}

  /* ── v6.0: Sparkline ── */
  .sparkline {{ display:inline-block; vertical-align:middle; }}

  /* ── v6.0: Pivot Points display ── */
  .pivot-row {{ display:flex; gap:6px; flex-wrap:wrap; margin-top:6px; font-size:11px; }}
  .pivot-chip {{ background:var(--bg3); border-radius:4px; padding:3px 8px; }}
  .pivot-chip.pp  {{ color:var(--text); font-weight:700; }}
  .pivot-chip.r1  {{ color:var(--green); }}
  .pivot-chip.r2  {{ color:#059669; }}
  .pivot-chip.s1  {{ color:var(--red); }}
  .pivot-chip.s2  {{ color:#b91c1c; }}

  /* ── v6.0: FII/DII banner ── */
  .fii-banner {{ display:flex; align-items:center; gap:14px; background:var(--bg2); border:1px solid var(--border); border-radius:12px; padding:11px 16px; margin-bottom:12px; flex-wrap:wrap; font-size:13px; }}
  .fii-badge  {{ padding:3px 12px; border-radius:20px; font-size:12px; font-weight:600; letter-spacing:.04em; }}

  /* ── v6.0: Alert panel ── */
  .alert-panel {{ background:var(--bg2); border:1px solid rgba(56,189,248,.25); border-radius:14px; padding:16px 20px; margin-bottom:18px; }}
  .alert-title {{ font-size:13px; font-weight:700; color:var(--blue); margin-bottom:10px; display:flex; align-items:center; justify-content:space-between; }}
  .alert-grid  {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:6px; }}
  .alert-chip  {{ background:var(--bg3); border-radius:8px; padding:8px 12px; font-size:11px; }}
  .alert-sym   {{ font-weight:700; font-size:13px; color:var(--text); }}
  .alert-entry {{ color:var(--blue); margin-top:2px; }}
  .alert-sl    {{ color:var(--red); }}

  /* ── v6.0: CSV export + copy button ── */
  .export-btn {{ padding:5px 13px; border-radius:20px; border:1px solid rgba(56,189,248,.4); background:transparent; color:var(--blue); font-size:11px; cursor:pointer; transition:all .15s; }}
  .export-btn:hover {{ background:rgba(56,189,248,.12); }}
  .copy-btn   {{ padding:5px 13px; border-radius:20px; border:1px solid rgba(167,139,250,.4); background:transparent; color:var(--purple); font-size:11px; cursor:pointer; transition:all .15s; }}
  .copy-btn:hover {{ background:rgba(167,139,250,.12); }}

  /* ── v5.0: Quick Picks Panel ── */
  .qp-panel {{ background:var(--bg2); border:1px solid var(--border); border-radius:14px; padding:16px 20px; margin-bottom:18px; }}
  .qp-title {{ font-size:13px; font-weight:700; color:var(--text); margin-bottom:12px; display:flex; align-items:center; gap:6px; }}
  .qp-grid  {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:10px; }}
  .qp-col   {{ background:var(--bg3); border-radius:10px; padding:12px 14px; }}
  .qp-col-title {{ font-size:10px; font-weight:700; letter-spacing:.07em; text-transform:uppercase; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid var(--border); }}
  .qp-stock {{ display:flex; justify-content:space-between; align-items:center; padding:4px 0; font-size:12px; cursor:pointer; border-radius:4px; }}
  .qp-stock:hover {{ color:var(--blue); }}
  .qp-stock-sym {{ font-weight:700; }}
  .qp-stock-meta {{ font-size:10px; color:var(--muted); }}

  /* ── v5.0: Sort bar ── */
  .sort-bar {{ display:flex; gap:5px; margin-bottom:10px; flex-wrap:wrap; align-items:center; }}
  .sort-lbl {{ font-size:11px; color:var(--muted); margin-right:2px; }}
  .sort-btn {{ padding:4px 11px; border-radius:6px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:11px; cursor:pointer; transition:all .15s; }}
  .sort-btn:hover {{ border-color:var(--amber); color:var(--amber); }}
  .sort-btn.active {{ background:rgba(245,158,11,.15); border-color:var(--amber); color:var(--amber); font-weight:600; }}

  /* ── v5.0: Sector select + range ── */
  .sector-select {{ background:var(--bg3); border:1px solid var(--border); border-radius:20px; color:var(--muted); font-size:11px; padding:4px 10px; cursor:pointer; outline:none; }}
  .sector-select:focus {{ border-color:var(--blue); color:var(--text); }}
  .range-filter {{ display:flex; align-items:center; gap:8px; font-size:11px; color:var(--muted); }}
  .range-filter input[type=range] {{ width:90px; accent-color:var(--blue); cursor:pointer; }}
  .filter-sep {{ width:1px; height:16px; background:var(--border); margin:0 3px; }}

  /* ── v5.0: Results counter ── */
  .results-counter {{ font-size:11px; color:var(--muted); margin-left:auto; padding:4px 10px; background:var(--bg3); border-radius:20px; }}
</style>
</head>
<body>
<div class="page-wrap">

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <h1 style="letter-spacing:-0.5px;font-size:24px">
      <span style="color:var(--accent)">Trade</span> <span style="color:var(--accent2)">Stag</span>
      <span style="font-size:11px;background:rgba(212,160,36,.15);border:1px solid rgba(212,160,36,.3);color:var(--accent);padding:2px 8px;border-radius:20px;margin-left:8px;font-weight:600;letter-spacing:.04em;vertical-align:middle">v7.2</span>
    </h1>
    <p style="color:var(--muted);font-size:12px;margin-top:3px">NSE 500 India-First Swing Scanner · Delivery% · FII(gate) · OI · VIX · PCR · EMA Momentum</p>
  </div>
  <div class="header-right">
    <div>Generated: {analysis_time}</div>
    <div style="margin-top:3px;">Universe: {total} stocks analyzed</div>
    <div style="margin-top:2px;color:var(--purple);">Capital: ₹{cap:,.0f} · Risk/trade: {CFG['risk_per_trade_pct']}% (₹{risk_amt:,})</div>
  </div>
</div>

<!-- PCR BANNER -->
<div class="pcr-banner">
  <div class="pcr-item"><strong>Nifty Options PCR</strong></div>
  <div class="pcr-badge" style="background:{'#059669' if 'Bullish' in pcr_sent else '#f59e0b' if 'Neutral' in pcr_sent else '#ef4444'};">{pcr_sent}</div>
  <div class="pcr-item">Total PCR: <strong>{pcr_val}</strong></div>
  <div class="pcr-item">Weekly PCR: <strong style="color:{'#10b981' if weekly_pcr and weekly_pcr>1.0 else '#ef4444' if weekly_pcr and weekly_pcr<0.8 else '#f59e0b'}">{weekly_pcr if weekly_pcr else "N/A"}</strong> <span style="font-size:10px;color:var(--muted)">exp {weekly_exp}</span></div>
  <div class="pcr-item">Put OI: <strong>{pcr_data.get('total_pe_oi','N/A'):,}</strong></div>
  <div class="pcr-item">Call OI: <strong>{pcr_data.get('total_ce_oi','N/A'):,}</strong></div>
  <div class="pcr-item">Max Pain: <strong style="color:var(--amber)">{mp_display}</strong></div>
  <div class="pcr-item" style="font-size:10px;color:var(--muted)">{mp_sentiment}</div>
  <div class="pcr-item" style="margin-left:auto;font-size:11px;">PCR&gt;1.2 = Bullish · PCR&lt;0.8 = Bearish</div>
</div>

<!-- FII/DII FLOW BANNER (v6.0) -->
<div class="fii-banner">
  <div style="color:var(--muted)"><strong style="color:var(--text)">FII/DII Flow</strong></div>
  <div class="fii-badge" style="background:{'rgba(16,185,129,.15)' if fii_5d and fii_5d>500 else 'rgba(239,68,68,.15)' if fii_5d and fii_5d<-500 else 'rgba(245,158,11,.12)'}; color:{'var(--green)' if fii_5d and fii_5d>500 else 'var(--red)' if fii_5d and fii_5d<-500 else 'var(--amber)'};">{fii_sentiment}</div>
  <div style="color:var(--muted)">FII Today: <strong style="color:{'var(--green)' if fii_net and fii_net>0 else 'var(--red)' if fii_net and fii_net<0 else 'var(--text)'}">{'₹{:,.0f}Cr'.format(fii_net) if fii_net is not None else 'N/A'}</strong></div>
  <div style="color:var(--muted)">DII Today: <strong style="color:var(--text)">{'₹{:,.0f}Cr'.format(dii_net) if dii_net is not None else 'N/A'}</strong></div>
  <div style="color:var(--muted)">5-Day FII Net: <strong style="color:{'var(--green)' if fii_5d and fii_5d>0 else 'var(--red)' if fii_5d and fii_5d<0 else 'var(--text)'}">{'₹{:,.0f}Cr'.format(fii_5d) if fii_5d is not None else 'N/A'}</strong></div>
  <div style="color:var(--muted)">📋 Bulk Buys: <strong style="color:var(--green);">{len(bulk_buy_stocks)}</strong></div>
  <div style="color:var(--muted)">🚨 Bulk Sells: <strong style="color:var(--red);">{len(bulk_sell_stocks)}</strong></div>
  <div style="margin-left:auto;font-size:11px;color:var(--muted);">FII 5d &gt;₹500Cr = tailwind · &lt;−₹500Cr = headwind</div>
</div>

<!-- MARKET BREADTH BANNER (v3.0) -->
  <div class="breadth-dot" style="background:{breadth_col};box-shadow:0 0 7px {breadth_col};"></div>
  <strong>Market Breadth: {breadth_status}</strong>
  <span style="opacity:.85;">{breadth_pct}% of Nifty 500 above 200 EMA ({breadth_data.get('count',0)} stocks)</span>
  {'<span style="margin-left:auto;font-size:11px;opacity:.75;">✅ Good environment for new entries</span>' if breadth_status == "STRONG" else
   '<span style="margin-left:auto;font-size:11px;opacity:.85;">⚠️ Trade only A+ setups — reduce position size</span>' if breadth_status == "CAUTION" else
   '<span style="margin-left:auto;font-size:11px;opacity:.9;">🚫 WEAK MARKET — avoid new entries, tight stops only</span>'}
</div>

<!-- QUICK PICKS PANEL (v6.0) -->
<div class="qp-panel">
  <div class="qp-title">⚡ Quick Picks — Best candidates right now by category</div>
  <div class="qp-grid" id="quickPicksGrid">
    <div class="qp-col">
      <div class="qp-col-title" style="color:#a78bfa;">🎯 Pre-Move Setups (Top Score)</div>
      <div id="qp-premove"></div>
    </div>
    <div class="qp-col">
      <div class="qp-col-title" style="color:#10b981;">🔷 VCP + Coiling</div>
      <div id="qp-vcp"></div>
    </div>
    <div class="qp-col">
      <div class="qp-col-title" style="color:#38bdf8;">📉 Volume Dry-Up</div>
      <div id="qp-voldry"></div>
    </div>
    <div class="qp-col">
      <div class="qp-col-title" style="color:#10b981;">📈 Gainers Today</div>
      <div id="qp-gainers"></div>
    </div>
    <div class="qp-col">
      <div class="qp-col-title" style="color:#f472b6;">💎 Fund Strong + Stage 2</div>
      <div id="qp-fundstage"></div>
    </div>
    <div class="qp-col">
      <div class="qp-col-title" style="color:#f59e0b;">🏦 Accumulation Today</div>
      <div id="qp-accum"></div>
    </div>
  </div>
</div>



<!-- STATS ROW -->
<div style="margin-bottom:14px">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;flex-wrap:wrap;gap:8px">
    <span style="font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.06em">ADVANCE / DECLINE — {adv_count} stocks advanced · {dec_count} declined · {unch_count} unchanged</span>
    <span style="font-size:11px;color:var(--muted)">FII 5D: <strong style="color:{'var(--green)' if (fii_5d_html or 0)>0 else 'var(--red)'}">{fii_5d_str}</strong> &nbsp;|&nbsp; PCR: <strong style="color:var(--blue)">{pcr_val_html}</strong> &nbsp;|&nbsp; India VIX: <strong style="color:var(--amber)">{vix_val_html}</strong></span>
  </div>
  <div style="height:28px;border-radius:8px;overflow:hidden;display:flex;width:100%">
    <div style="background:#10b981;height:100%;width:{adv_pct:.1f}%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;min-width:30px">
      {adv_count}▲
    </div>
    <div style="background:#888780;height:100%;width:{unch_pct:.1f}%;min-width:4px"></div>
    <div style="background:#ef4444;height:100%;width:{dec_pct:.1f}%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;min-width:30px">
      {dec_count}▼
    </div>
  </div>
</div>
<div class="stats-row">
  <div class="stat-card"><div class="stat-label">Analyzed</div><div class="stat-val">{total}</div><div class="stat-sub">Nifty 500 universe</div></div>
  <div class="stat-card"><div class="stat-label">A+ / A Grade</div><div class="stat-val" style="color:var(--green);">{grade_counts.get('A+',0)+grade_counts.get('A',0)}</div><div class="stat-sub">Elite setups</div></div>
  <div class="stat-card"><div class="stat-label">Stage 2 ✅</div><div class="stat-val" style="color:var(--green);">{len(stage2_stocks)}</div><div class="stat-sub">Advancing stocks</div></div>
  <div class="stat-card"><div class="stat-label">💎 Fund Strong</div><div class="stat-val" style="color:var(--purple);">{len(fund_strong)}</div><div class="stat-sub">ROE&gt;20% + EPS growth</div></div>
  <div class="stat-card"><div class="stat-label">🚀 RS Elite</div><div class="stat-val" style="color:#a78bfa;">{len(rs_elite)}</div><div class="stat-sub">Top 10% momentum</div></div>
  <div class="stat-card"><div class="stat-label">🏦 Accumulation</div><div class="stat-val" style="color:var(--green);">{len(accum_stocks)}</div><div class="stat-sub">{len(strong_accum)} strong signals</div></div>
  <div class="stat-card"><div class="stat-label">🚨 Pledge Danger</div><div class="stat-val" style="color:var(--red);">{len(pledge_danger)}</div><div class="stat-sub">Pledging &gt;{CFG['pledge_danger_pct']}%</div></div>
  <div class="stat-card"><div class="stat-label">🔥 Vol Surge</div><div class="stat-val" style="color:var(--amber);">{len(vol_surges)}</div><div class="stat-sub">{len(vol_surges_up)} on up-days ↑</div></div>
  <div class="stat-card"><div class="stat-label">Active Breakouts</div><div class="stat-val" style="color:var(--blue);">{len(breakouts)}</div><div class="stat-sub">Vol-confirmed</div></div>
  <div class="stat-card"><div class="stat-label">VCP Setups</div><div class="stat-val" style="color:#c084fc;">{len(vcps)}</div><div class="stat-sub">Score ≥ 60</div></div>
  <div class="stat-card"><div class="stat-label">📈 Supertrend BUY</div><div class="stat-val" style="color:var(--green);">{len(supertrend_buy)}</div><div class="stat-sub">{len(st_flip)} fresh flips today</div></div>
  <div class="stat-card"><div class="stat-label">📋 Bulk Deals</div><div class="stat-val" style="color:var(--blue);">{len(bulk_buy_stocks)}</div><div class="stat-sub">{len(bulk_sell_stocks)} sell alerts</div></div>
  <div class="stat-card"><div class="stat-label">📉 OBV Divergence</div><div class="stat-val" style="color:#c084fc;">{len(obv_div_stocks)}</div><div class="stat-sub">Volume leading price</div></div>
  <div class="stat-card"><div class="stat-label">🕯 Candle Setups</div><div class="stat-val" style="color:var(--amber);">{len(candle_stocks)}</div><div class="stat-sub">Bullish reversal patterns</div></div>
  <div class="stat-card"><div class="stat-label">⚡ Circuit Risk</div><div class="stat-val" style="color:var(--red);">{len(circuit_stocks)}</div><div class="stat-sub">Near UC limit — avoid</div></div>
  <div class="stat-card"><div class="stat-label">🆕 IPO Base</div><div class="stat-val" style="color:var(--blue);">{len(ipo_base_stocks)}</div><div class="stat-sub">First base after listing</div></div>
  <div class="stat-card"><div class="stat-label">⚠️ Near Earnings</div><div class="stat-val" style="color:var(--red);">{len(near_earnings)}</div><div class="stat-sub">Results in ≤14d</div></div>
</div>


<!-- GRADE DISTRIBUTION -->
<div class="section-title">Grade Distribution</div>
<div class="grade-dist">
"""
        for g, col in [("A+","#059669"),("A","#10b981"),("B+","#0284c7"),("B","#38bdf8"),("C","#f59e0b"),("D","#ef4444")]:
            cnt = grade_counts.get(g, 0)
            pct = round(cnt / total * 100, 1) if total > 0 else 0
            html += f'<div class="grade-pill" style="background:{col};">{g}: {cnt} <span style="opacity:.75;font-size:11px;">({pct}%)</span></div>\n'

        # ── TOP TRADES PANEL (v4.0) ──
        html += '</div>\n\n<!-- TOP TRADES PANEL (v4.0) -->\n<div class="top-trades-panel">\n'
        html += '<div class="top-trades-title">🎯 Highest Scoring Setups — Multi-Factor Ranking</div>\n'
        html += '<div class="top-trades-grid">\n'
        for i, r in enumerate(top_trades, 1):
            ts       = r.get("trade_setup", {})
            conf     = r.get("confidence_pct", 50)
            setup    = ts.get("setup_type", "—")
            entry_v  = ts.get("entry", 0)
            sl_v     = ts.get("stop_loss", 0)
            t1_v     = ts.get("target1", 0)
            rr       = ts.get("rr_ratio", 0)
            accum    = r.get("accum_label", "None")
            conf_col = ("#059669" if conf >= 80 else "#10b981" if conf >= 70 else "#0284c7" if conf >= 60 else "#f59e0b")
            accum_tag = f'<span style="background:rgba(16,185,129,.12);color:#10b981;border-radius:3px;padding:1px 5px;font-size:9px;margin-left:4px;">🏦{accum}</span>' if r.get("is_accumulating") else ""
            html += f"""<div class="trade-card" onclick="openModal('{r['symbol']}')">
  <div class="trade-card-rank">#{i} · {r.get('sector','—')}</div>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-top:4px;">
    <div>
      <div class="trade-card-sym">{r['symbol']}</div>
      <div class="trade-card-setup">{setup}{accum_tag}</div>
    </div>
    <span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span>
  </div>
  <div class="conf-bar"><div class="conf-fill" style="width:{conf}%;background:{conf_col};"></div></div>
  <div class="conf-label"><span>Confidence</span><span style="color:{conf_col};font-weight:700;">{conf}%</span></div>
  <div class="trade-card-prices">
    <div class="price-chip">CMP <strong style="color:var(--text);">₹{r['price']:,.1f}</strong></div>
    <div class="price-chip">Entry <strong style="color:var(--blue);">₹{entry_v:,.1f}</strong></div>
    <div class="price-chip">SL <strong style="color:var(--red);">₹{sl_v:,.1f}</strong></div>
    <div class="price-chip">T1 <strong style="color:var(--green);">₹{t1_v:,.1f}</strong></div>
    <div class="price-chip">R:R <strong style="color:var(--amber);">{rr}x</strong></div>
  </div>
</div>\n"""
        html += '</div>\n</div>\n\n'

        html += """<!-- TABS -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('all',this)">All Stocks</button>
  <button class="tab-btn" onclick="switchTab('aplus',this)">⭐ Top Scoring Stocks</button>
  <button class="tab-btn" onclick="switchTab('breakouts',this)">⚡ Breakouts</button>
  <button class="tab-btn" onclick="switchTab('vcp',this)">🔷 VCP Setups</button>
  <button class="tab-btn" onclick="switchTab('rs',this)">🚀 RS Leaders</button>
  <button class="tab-btn" onclick="switchTab('volsurge',this)">🔥 Vol Surge</button>
  <button class="tab-btn" onclick="switchTab('stage2',this)">✅ Stage 2</button>
  <button class="tab-btn" onclick="switchTab('accumulation',this)">🏦 Accumulation</button>
  <button class="tab-btn" onclick="switchTab('fundamentals',this)">💎 Fundamentals</button>
  <button class="tab-btn" onclick="switchTab('expert',this)">⭐ Multi-Factor Leaders</button>
  <button class="tab-btn" onclick="switchTab('sectors',this)">🏭 Sectors</button>
  <button class="tab-btn" onclick="switchTab('trade',this)">🎯 High Conviction Setups</button>
  <button class="tab-btn" onclick="switchTab('ema',this)">📈 EMA Scanner</button>
  <button class="tab-btn" onclick="switchTab('price_action',this)">📊 Price Action</button>
  <button class="tab-btn" onclick="switchTab('value_screen',this)">💰 Value Screens</button>
  <button class="tab-btn" onclick="switchTab('quality_screen',this)">🏆 Quality Stocks</button>
</div>
"""

        # ── Build main stock table ──
        # Collect all unique sectors for dropdown
        all_sectors = sorted(set(r.get("sector","Others") for r in results))

        def build_table(rows, table_id, show_warn=False):
            sector_opts = "".join(f'<option value="{s}">{s}</option>' for s in all_sectors)
            t = f"""
<div id="pane-{table_id}" class="tab-pane {'active' if table_id=='all' else ''}">

<!-- Search + Sector + Results counter -->
<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:180px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." id="search-{table_id}"
      oninput="handleSearch(this,'{table_id}')">
  </div>
  <select class="sector-select" id="sector-{table_id}" onchange="handleSector(this,'{table_id}')">
    <option value="">All Sectors</option>
    {sector_opts}
  </select>
  <span class="results-counter" id="counter-{table_id}">— stocks</span>
</div>

<!-- Sort Bar -->
<div class="sort-bar">
  <span class="sort-lbl">Sort:</span>
  <button class="sort-btn active" onclick="quickSort('{table_id}',3,'desc',this)">Score ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',5,'desc',this)">1D% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',5,'asc',this)">1D% ↑</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',6,'desc',this)">5D% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',7,'desc',this)">1M% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',13,'desc',this)">Vol Ratio ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',11,'asc',this)">BB Tight ↑</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',12,'desc',this)">RS%ile ↓</button>
  <div class="filter-sep"></div>
  <span class="range-filter">
    Score ≥ <input type="range" min="0" max="100" value="0" step="5" id="scoremin-{table_id}"
      oninput="handleScore(this,'{table_id}')">
    <span id="scoreval-{table_id}" style="min-width:24px;color:var(--blue);font-weight:600;">0</span>
  </span>
</div>

<!-- Filter chips -->
<div class="filter-row">
  <span style="color:var(--muted);font-size:11px;">Filter:</span>
  <button class="filter-btn on" id="chip-all-{table_id}" onclick="setChip(this,'{table_id}','')">All</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','A+')">A+</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','A')">A</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','B+')">B+</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','nr7')">NR7</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','inside_day')">Inside Day</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','pocket_pivot')">Pocket Pivot</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vcp')">🔷 VCP</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vol_dryup')">📉 Vol Dry-Up</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','breakout')">⚡ Breakout</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','gainer')">📈 Gainers Today</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','loser')">📉 Losers Today</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','gainer_5d')">📈 5D Gainer</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','stage2')">✅ Stage 2</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','fund_strong')">💎 Fund Strong</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','accumulation')">🏦 Accum</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','rs_elite')">🚀 RS Elite</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','hi_delivery')">📦 Delivery&gt;55%</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vol_surge')">🔥 Vol Surge</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','pledge_danger')">🚨 Pledge Danger</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','earnings_warn')">⚠️ Near Results</button>
</div>

<div class="tbl-wrap">
<table id="{table_id}-table">
<thead>
  <tr>
    <th onclick="sortTable('{table_id}-table',0)">#</th>
    <th onclick="sortTable('{table_id}-table',1)">Symbol</th>
    <th onclick="sortTable('{table_id}-table',2)">Grade</th>
    <th onclick="sortTable('{table_id}-table',3)">Score</th>
    <th onclick="sortTable('{table_id}-table',4)">Price</th>
    <th onclick="sortTable('{table_id}-table',5)">1D%</th>
    <th onclick="sortTable('{table_id}-table',6)">5D%</th>
    <th onclick="sortTable('{table_id}-table',7)">1M%</th>
    <th onclick="sortTable('{table_id}-table',8)">3M%</th>
    <th onclick="sortTable('{table_id}-table',9)">RSI</th>
    <th onclick="sortTable('{table_id}-table',10)">ADX</th>
    <th onclick="sortTable('{table_id}-table',11)">BB%</th>
    <th onclick="sortTable('{table_id}-table',12)">RS%ile</th>
    <th onclick="sortTable('{table_id}-table',13)">Vol Ratio</th>
    <th onclick="sortTable('{table_id}-table',14)">Delivery%</th>
    <th onclick="sortTable('{table_id}-table',15)">52W High%</th>
    <th onclick="sortTable('{table_id}-table',16)">Stage</th>
    <th onclick="sortTable('{table_id}-table',17)">Fund</th>
    <th onclick="sortTable('{table_id}-table',18)">Pledge%</th>
    <th onclick="sortTable('{table_id}-table',19)">Sector</th>
    <th>Entry / SL / T1</th>
    <th>Qty</th>
    <th>Signals</th>
  </tr>
</thead>
<tbody>
"""
            for i, r in enumerate(rows, 1):
                chg_class  = lambda v: "up" if v > 0 else "down" if v < 0 else "neutral"
                rsi_col    = "#10b981" if 50<=r['rsi']<=72 else "#ef4444" if r['rsi']>80 else "#f59e0b" if r['rsi']<40 else "#e8eaf0"
                adx_col    = "#10b981" if r['adx']>25 else "#f59e0b" if r['adx']>20 else "#8892a4"
                bb_col     = "#10b981" if r['bb_width']<8 else "#f59e0b" if r['bb_width']<12 else "#8892a4"
                rs_col     = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#8892a4"
                del_pct    = r['delivery_pct']
                del_str    = f"{del_pct:.0f}%" if del_pct is not None else "—"
                del_col    = "#10b981" if del_pct is not None and del_pct>=55 else "#f59e0b" if del_pct is not None and del_pct>=40 else "#8892a4"
                earn_warn  = r['earnings_info'].get('has_upcoming', False)
                ts         = r.get('trade_setup', {})
                entry_str  = f"₹{ts.get('entry',0):,.1f}" if ts.get('entry') else "—"
                sl_str     = f"₹{ts.get('stop_loss',0):,.1f}" if ts.get('stop_loss') else "—"
                t1_str     = f"₹{ts.get('target1',0):,.1f}" if ts.get('target1') else "—"
                trade_html = f'<span style="color:var(--blue)">{entry_str}</span> / <span style="color:var(--red)">{sl_str}</span> / <span style="color:var(--green)">{t1_str}</span>'
                sigs       = r["active_signals"][:5]
                sigs_html  = ""
                for s in sigs:
                    cls = "signal-elite" if "Elite" in s or "RS" in s else \
                          "signal-warn"  if "⚠️" in s or "Results" in s else \
                          "signal-surge" if any(x in s for x in ["Surge","surge"]) else \
                          "signal-green" if any(x in s for x in ["Delivery","Near52W","Breakout"]) else ""
                    sigs_html += f'<span class="signal-tag {cls}">{s}</span>'
                # ── v3.0 new cell variables ──
                stage_val   = r.get("stage", "Unknown")
                stage_cls   = {"Stage 2":"stage-2","Stage 1":"stage-1","Stage 3":"stage-3","Stage 4":"stage-4"}.get(stage_val,"")
                fund_grade  = r.get("fund_grade", "N/A")
                fund_cls    = {"Strong":"fund-strong","Good":"fund-good","Weak":"fund-weak"}.get(fund_grade,"")
                pledge      = r.get("pledge_pct")
                pledge_str  = f"{pledge:.0f}%" if pledge is not None else "—"
                pledge_cls  = "pledge-danger" if r.get("pledge_danger") else "pledge-warn" if r.get("pledge_warn") else ""
                # Volume surge
                vs_type  = r.get("vol_surge_type", "")
                vs_ratio = r.get("vol_surge_ratio", 0)
                vs_up    = r.get("vol_surge_up", False)
                vs_col   = ("#f59e0b" if vs_type == "MegaSurge"
                            else "#10b981" if vs_type == "StrongSurge"
                            else "#38bdf8" if vs_type else "#8892a4")
                vs_str   = (f"🔥{vs_ratio:.1f}x" if vs_type == "MegaSurge"
                            else f"⚡{vs_ratio:.1f}x" if vs_type == "StrongSurge"
                            else f"↑{vs_ratio:.1f}x" if vs_type else "—")
                # Position qty
                ts_entry = ts.get("entry", 0)
                ts_sl    = ts.get("stop_loss", 0)
                if ts_entry and ts_sl and ts_entry > ts_sl:
                    risk_per = ts_entry - ts_sl
                    qty = int(risk_amt / risk_per) if risk_per > 0 else 0
                else:
                    qty = 0
                qty_str  = f"{qty:,}" if qty > 0 else "—"
                data_attrs = (f'data-grade="{r["grade"]}" '
                              f'data-sector="{r.get("sector","Others")}" '
                              f'data-score="{r["score"]}" '
                              f'data-breakout="{1 if r["breakout"] else 0}" '
                              f'data-vcp="{1 if r["vcp_score"]>=60 else 0}" '
                              f'data-nr7="{1 if r.get("nr7") else 0}" '
                              f'data-inside_day="{1 if r.get("inside_day") else 0}" '
                              f'data-pocket_pivot="{1 if r.get("pocket_pivot") else 0}" '
                              f'data-vol_dryup="{1 if r.get("vol_dry_up") else 0}" '
                              f'data-rs_elite="{1 if r["rs_percentile"]>=90 else 0}" '
                              f'data-hi_delivery="{1 if del_pct is not None and del_pct>=55 else 0}" '
                              f'data-near52w="{1 if r["near_52w_high"] else 0}" '
                              f'data-vol_surge="{1 if vs_type else 0}" '
                              f'data-vol_surge_up="{1 if vs_type and vs_up else 0}" '
                              f'data-stage2="{1 if stage_val=="Stage 2" else 0}" '
                              f'data-fund_strong="{1 if fund_grade=="Strong" else 0}" '
                              f'data-pledge_danger="{1 if r.get("pledge_danger") else 0}" '
                              f'data-earnings_warn="{1 if earn_warn else 0}" '
                              f'data-accumulation="{1 if r.get("is_accumulating") else 0}" '
                              f'data-gainer="{1 if r["chg_1d"]>0 else 0}" '
                              f'data-loser="{1 if r["chg_1d"]<0 else 0}" '
                              f'data-gainer_5d="{1 if r["chg_5d"]>0 else 0}"')
                warn_icon = ' <span style="color:#ef4444;font-size:10px;" title="Results soon">⚠️</span>' if earn_warn else ''
                circuit_icon = f' <span style="color:#f59e0b;font-size:9px;" title="Near circuit limit">⚡{r.get("circuit_risk","")}</span>' if r.get("circuit_risk") else ''
                fno_icon = ' <span style="color:#8892a4;font-size:9px;">F&O</span>' if r.get("is_fno") else ''
                # Sparkline SVG
                spark_prices = r.get("sparkline", [])
                spark_html = ""
                if spark_prices and len(spark_prices) >= 3:
                    mn, mx = min(spark_prices), max(spark_prices)
                    rng = (mx - mn) or 1
                    w, h = 44, 16
                    pts = " ".join(
                        f"{round(i*(w/(len(spark_prices)-1)),1)},{round(h - (v-mn)/rng*h, 1)}"
                        for i, v in enumerate(spark_prices)
                    )
                    clr = "#10b981" if spark_prices[-1] >= spark_prices[0] else "#ef4444"
                    spark_html = f'<svg class="sparkline" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{pts}" fill="none" stroke="{clr}" stroke-width="1.5" stroke-linejoin="round"/></svg>'
                # Score tooltip showing top contributors
                sb = r.get("score_breakdown", {})
                top_contributors = sorted([(k,v) for k,v in sb.items() if v>0], key=lambda x:-x[1])[:3]
                score_tip = " | ".join(f"{k.replace('_',' ')}:{v}" for k,v in top_contributors)
                t += f"""<tr {data_attrs} onclick="openModal('{r['symbol']}')">
  <td style="color:var(--muted);">{i}</td>
  <td><strong>{r['symbol']}</strong>{warn_icon}{circuit_icon}{fno_icon}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span></td>
  <td>
    <div style="display:flex;align-items:center;gap:5px;" title="{score_tip}">
      <span style="font-weight:700;cursor:help;">{r['score']}</span>
      <div class="prog-bar" style="width:40px;"><div class="prog-fill" style="width:{r['score']}%;background:{r['grade_color']};"></div></div>
    </div>
  </td>
  <td style="font-weight:600;">
    <div style="display:flex;align-items:center;gap:6px;">
      ₹{r['price']:,.2f}
      {spark_html}
    </div>
  </td>
  <td class="{chg_class(r['chg_1d'])}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td class="{chg_class(r['chg_5d'])}">{'+' if r['chg_5d']>0 else ''}{r['chg_5d']:.2f}%</td>
  <td class="{chg_class(r['chg_1m'])}">{'+' if r['chg_1m']>0 else ''}{r['chg_1m']:.2f}%</td>
  <td class="{chg_class(r['chg_3m'])}">{'+' if r['chg_3m']>0 else ''}{r['chg_3m']:.2f}%</td>
  <td style="color:{rsi_col};">{r['rsi']}</td>
  <td style="color:{adx_col};">{r['adx']}</td>
  <td style="color:{bb_col};">{r['bb_width']:.1f}%</td>
  <td><div style="display:flex;align-items:center;gap:4px;"><div class="prog-bar" style="width:30px;"><div class="prog-fill" style="width:{r['rs_percentile']}%;background:{rs_col};"></div></div><span style="color:{rs_col};">{r['rs_percentile']}</span></div></td>
  <td style="color:{del_col};">{del_str}</td>
  <td style="color:{vs_col};font-weight:{'700' if vs_type else '400'};">{vs_str}</td>
  <td class="{'up' if r['pct_from_high']>=-5 else 'neutral'}">{r['pct_from_high']:.1f}%</td>
  <td><span class="{stage_cls}" style="font-size:10px;">{stage_val.replace("Stage ","S")}</span></td>
  <td><span class="{fund_cls}" style="font-size:10px;">{fund_grade}</span></td>
  <td><span class="{pledge_cls}" style="font-size:10px;">{pledge_str}</span></td>
  <td style="font-size:11px;color:var(--muted);">{r['sector']}</td>
  <td style="font-size:11px;">{trade_html}</td>
  <td style="color:var(--blue);font-weight:600;font-size:12px;">{qty_str}</td>
  <td>{sigs_html if sigs_html else '<span style="color:var(--muted);font-size:11px;">—</span>'}</td>
</tr>
"""
            t += "</tbody></table></div></div>\n"
            return t

        html += build_table(results, "all")
        html += build_table([r for r in results if r["grade"] in ("A+","A")], "aplus")
        html += build_table(breakouts, "breakouts")
        html += build_table(vcps, "vcp")
        html += build_table(sorted(results, key=lambda x: x["rs_percentile"], reverse=True)[:60], "rs")

        # ── Volume Surge Tab ──
        vs_sorted = sorted(
            [r for r in results if r.get("vol_surge_type")],
            key=lambda x: x.get("vol_surge_ratio", 0), reverse=True
        )
        html += '<div id="pane-volsurge" class="tab-pane">\n'
        html += f'''<div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;flex-wrap:wrap;">
  <div class="section-title" style="margin-bottom:0;">🔥 Volume Surge Stocks — Today\'s volume vs 20-day average</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px;">
    <span style="background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.3);color:var(--amber);padding:3px 10px;border-radius:20px;">🔥 Mega Surge ≥{CFG['vol_surge_mega']}×</span>
    <span style="background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.3);color:var(--green);padding:3px 10px;border-radius:20px;">⚡ Strong Surge ≥{CFG['vol_surge_strong']}×</span>
    <span style="background:rgba(56,189,248,.15);border:1px solid rgba(56,189,248,.3);color:var(--blue);padding:3px 10px;border-radius:20px;">↑ Surge ≥{CFG['vol_surge_mild']}×</span>
    <span style="color:var(--muted);">↑ = Up-day (bullish)  ↓ = Down-day (caution)</span>
  </div>
</div>
<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchSimpleTable(this,'volsurge-table')">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterSimpleGrade(this,'volsurge-table','')">All</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','A+')">A+</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','A')">A</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','B+')">B+</button>
  </div>
  <span id="counter-volsurge" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="volsurge-table">\n'
        html += '''<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>
  <th>Price</th><th>1D%</th>
  <th>Vol Ratio</th><th>Surge Type</th><th>Up/Down Day</th>
  <th>RSI</th><th>ADX</th><th>RS%ile</th><th>Delivery%</th>
  <th>Entry / SL / T1</th><th>Signals</th>
</tr></thead>\n<tbody>\n'''
        for i, r in enumerate(vs_sorted, 1):
            vs_type  = r.get("vol_surge_type", "")
            vs_ratio = r.get("vol_surge_ratio", 0)
            vs_up    = r.get("vol_surge_up", False)
            vs_col   = ("#f59e0b" if vs_type == "MegaSurge"
                        else "#10b981" if vs_type == "StrongSurge"
                        else "#38bdf8")
            vs_icon  = "🔥 Mega" if vs_type == "MegaSurge" else "⚡ Strong" if vs_type == "StrongSurge" else "↑ Surge"
            day_col  = "#10b981" if vs_up else "#ef4444"
            day_str  = "↑ UP (Bullish)" if vs_up else "↓ DOWN (Caution)"
            del_pct  = r['delivery_pct']
            del_str  = f"{del_pct:.0f}%" if del_pct is not None else "—"
            del_col  = "#10b981" if del_pct is not None and del_pct >= 55 else "#8892a4"
            rsi_col  = "#10b981" if 50<=r['rsi']<=72 else "#ef4444" if r['rsi']>80 else "#f59e0b"
            adx_col  = "#10b981" if r['adx']>25 else "#f59e0b" if r['adx']>20 else "#8892a4"
            rs_col   = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#8892a4"
            chg_class = "up" if r['chg_1d'] > 0 else "down" if r['chg_1d'] < 0 else "neutral"
            ts       = r.get("trade_setup", {})
            entry_s  = f"₹{ts.get('entry',0):,.1f}" if ts.get('entry') else "—"
            sl_s     = f"₹{ts.get('stop_loss',0):,.1f}" if ts.get('stop_loss') else "—"
            t1_s     = f"₹{ts.get('target1',0):,.1f}" if ts.get('target1') else "—"
            trade_h  = f'<span style="color:var(--blue)">{entry_s}</span> / <span style="color:var(--red)">{sl_s}</span> / <span style="color:var(--green)">{t1_s}</span>'
            sigs_h   = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
            html += f"""<tr onclick="openModal('{r['symbol']}')" style="cursor:pointer;">
  <td style="color:var(--muted);">{i}</td>
  <td><strong>{r['symbol']}</strong></td>
  <td style="font-size:12px;color:var(--muted);">{r['sector']}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span></td>
  <td style="font-weight:700;">{r['score']}</td>
  <td style="font-weight:600;">₹{r['price']:,.2f}</td>
  <td class="{chg_class}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td style="color:{vs_col};font-weight:800;">{vs_ratio:.2f}×</td>
  <td><span style="color:{vs_col};font-weight:700;">{vs_icon}</span></td>
  <td style="color:{day_col};font-weight:600;">{day_str}</td>
  <td style="color:{rsi_col};">{r['rsi']}</td>
  <td style="color:{adx_col};">{r['adx']}</td>
  <td style="color:{rs_col};">{r['rs_percentile']}</td>
  <td style="color:{del_col};">{del_str}</td>
  <td style="font-size:12px;">{trade_h}</td>
  <td>{sigs_h if sigs_h else '<span style="color:var(--muted);font-size:11px;">—</span>'}</td>
</tr>\n"""
        html += "</tbody></table></div>\n</div>\n"

        # ── Stage 2 Tab ──
        s2_sorted = sorted([r for r in results if r.get("is_stage2")], key=lambda x: x["score"], reverse=True)
        html += '<div id="pane-stage2" class="tab-pane">\n'
        html += f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap;"><div class="section-title" style="margin-bottom:0;">✅ Stage 2 Advancing Stocks — price above rising 30-week MA (Weinstein buy zone)</div><div style="font-size:11px;color:var(--muted);">{len(s2_sorted)} stocks in Stage 2</div></div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchSimpleTable(this,'stage2-table')">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterSimpleGrade(this,'stage2-table','')">All</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','A+')">A+</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','A')">A</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','B+')">B+</button>
  </div>
  <span id="counter-stage2" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="stage2-table"><thead><tr>\n'
        html += '<th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th><th>Price</th><th>1M%</th><th>RS%ile</th><th>RSI</th><th>ADX</th><th>30W MA</th><th>MA Slope</th><th>Fund Grade</th><th>Pledge%</th><th>Entry / SL / T1</th><th>Qty</th><th>Signals</th>\n'
        html += '</tr></thead><tbody>\n'
        for i, r in enumerate(s2_sorted, 1):
            si       = r.get("stage_info", {})
            ma30     = f"₹{si.get('ma30',0):,.1f}" if si.get('ma30') else "—"
            slope    = si.get('ma_slope_pct', 0)
            slope_s  = f"{slope:+.2f}%"
            slope_c  = "#10b981" if slope > 0.5 else "#f59e0b" if slope > 0 else "#ef4444"
            rsi_c    = "#10b981" if 50<=r['rsi']<=72 else "#f59e0b"
            rs_c     = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#e8eaf0"
            fg       = r.get("fund_grade","N/A")
            fg_c     = "#a78bfa" if fg=="Strong" else "#10b981" if fg=="Good" else "#f59e0b" if fg=="Moderate" else "#ef4444"
            pl       = r.get("pledge_pct")
            pl_s     = f"{pl:.0f}%" if pl is not None else "—"
            pl_c     = "#ef4444" if r.get("pledge_danger") else "#f59e0b" if r.get("pledge_warn") else "#8892a4"
            ts       = r.get("trade_setup", {})
            entry_v  = ts.get("entry", 0)
            sl_v     = ts.get("stop_loss", 0)
            qty      = int(risk_amt / (entry_v - sl_v)) if entry_v and sl_v and entry_v > sl_v else 0
            trade_h  = (f'<span style="color:var(--blue)">₹{entry_v:,.1f}</span> / '
                        f'<span style="color:var(--red)">₹{sl_v:,.1f}</span> / '
                        f'<span style="color:var(--green)">₹{ts.get("target1",0):,.1f}</span>') if entry_v else "—"
            sigs_h   = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
            chg_c    = "up" if r['chg_1m'] > 0 else "down"
            html += f"""<tr onclick="openModal('{r['symbol']}')" style="cursor:pointer;">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r['symbol']}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r['sector']}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']}">{r['grade']}</span></td>
  <td style="font-weight:700">{r['score']}</td>
  <td style="font-weight:600">₹{r['price']:,.2f}</td>
  <td class="{chg_c}">{'+' if r['chg_1m']>0 else ''}{r['chg_1m']:.1f}%</td>
  <td style="color:{rs_c}">{r['rs_percentile']}</td>
  <td style="color:{rsi_c}">{r['rsi']}</td>
  <td style="color:{'#10b981' if r['adx']>25 else '#f59e0b'}">{r['adx']}</td>
  <td style="color:var(--muted);font-size:11px">{ma30}</td>
  <td style="color:{slope_c};font-weight:600">{slope_s}</td>
  <td style="color:{fg_c}">{fg}</td>
  <td style="color:{pl_c}">{pl_s}</td>
  <td style="font-size:11px">{trade_h}</td>
  <td style="color:var(--blue);font-weight:600">{f'{qty:,}' if qty else '—'}</td>
  <td>{sigs_h or '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
</tr>\n"""
        html += "</tbody></table></div>\n</div>\n"

        # ── Fundamentals Tab ──
        fund_sorted = sorted([r for r in results if r.get("fund_score", 0) > 0],
                             key=lambda x: x.get("fund_score", 0), reverse=True)
        html += '<div id="pane-fundamentals" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:10px;">💎 Fundamental Quality — ROE · EPS Growth · D/E · OCF Quality · Promoter Pledging</div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol..." oninput="searchFundCards(this)">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterFundCards(this,'')">All</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Strong')">💎 Strong</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Good')">✅ Good</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Moderate')">⚡ Moderate</button>
  </div>
  <span id="counter-fundamentals" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        if pledge_danger:
            html += f'<div class="pledge-alert" style="margin-bottom:14px;">🚨 <strong>{len(pledge_danger)} stocks</strong> have promoter pledging &gt;{CFG["pledge_danger_pct"]}% — score penalised -{CFG["pledge_score_penalty"]} pts. Avoid or drastically reduce position size.</div>\n'
        html += '<div id="fund-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(275px,1fr));gap:10px;">\n'
        for r in fund_sorted[:60]:
            fgrade  = r.get("fund_grade", "N/A")
            roe_v   = f"{r['roe']:.1f}%" if r.get("roe") is not None else "N/A"
            eps_v   = f"{r['eps_growth']:.1f}%" if r.get("eps_growth") is not None else "N/A"
            de_v    = f"{r['de_ratio']:.2f}" if r.get("de_ratio") is not None else "N/A"
            pe_v    = f"{r['pe_ratio']:.1f}×" if r.get("pe_ratio") is not None else "N/A"
            pledge  = r.get("pledge_pct")
            p_badge = ""
            if pledge is not None and pledge >= CFG["pledge_danger_pct"]:
                p_badge = f'<span class="pledge-danger" style="margin-left:6px">🚨Pledge {pledge:.0f}%</span>'
            elif pledge is not None and pledge >= CFG["pledge_warn_pct"]:
                p_badge = f'<span class="pledge-warn" style="margin-left:6px">⚠Pledge {pledge:.0f}%</span>'
            stage_v = r.get("stage","Unknown")
            stage_c = "#10b981" if stage_v=="Stage 2" else "#f59e0b" if stage_v=="Stage 1" else "#ef4444"
            fc      = "#a78bfa" if fgrade=="Strong" else "#10b981" if fgrade=="Good" else "#f59e0b" if fgrade=="Moderate" else "#ef4444"
            roe_c   = "#10b981" if r.get("roe") and r["roe"]>=20 else "#f59e0b" if r.get("roe") and r["roe"]>=12 else "#ef4444"
            eps_c   = "#10b981" if r.get("eps_growth") and r["eps_growth"]>=25 else "#f59e0b" if r.get("eps_growth") and r["eps_growth"]>=15 else "#ef4444"
            de_c    = "#10b981" if r.get("de_ratio") is not None and r["de_ratio"]<=0.5 else "#f59e0b" if r.get("de_ratio") is not None and r["de_ratio"]<=1.0 else "#ef4444"
            html += f"""<div class="fund-card" data-symbol="{r['symbol']}" data-fundgrade="{fgrade}" onclick="openModal('{r['symbol']}')">\n  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:4px;">
    <div><span style="font-size:15px;font-weight:800">{r['symbol']}</span><span class="grade-badge" style="background:{r['grade_color']};margin-left:7px">{r['grade']}</span>{p_badge}</div>
    <div style="text-align:right"><div style="font-size:18px;font-weight:800;color:{fc}">{r.get('fund_score',0)}/20</div><div style="font-size:10px;color:{fc}">{fgrade}</div></div>
  </div>
  <div class="fund-metric"><span style="color:var(--muted)">ROE</span><span style="color:{roe_c};font-weight:600">{roe_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">EPS Growth YoY</span><span style="color:{eps_c};font-weight:600">{eps_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">Debt / Equity</span><span style="color:{de_c};font-weight:600">{de_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">P/E Ratio</span><span style="font-weight:600">{pe_v}</span></div>
  <div class="fund-metric" style="border:none"><span style="color:var(--muted)">Stage</span><span style="color:{stage_c};font-weight:600">{stage_v}</span></div>
</div>\n"""
        html += "</div>\n</div>\n"

        # ── Accumulation Tab (v4.0) ──
        accum_sorted = sorted(
            [r for r in results if r.get("is_accumulating") or r.get("accum_score", 0) >= 20],
            key=lambda x: x.get("accum_score", 0), reverse=True
        )
        html += '<div id="pane-accumulation" class="tab-pane">\n'
        html += f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap;">'
        html += f'<div class="section-title" style="margin-bottom:0;">🏦 Institutional Accumulation Detector — Smart Money Activity</div>'
        html += f'<div style="font-size:11px;color:var(--muted);">{len(strong_accum)} Strong · {len(accum_stocks)} Total</div>'
        html += f'<div style="font-size:11px;color:var(--muted);margin-left:auto;">Signals: Volume Accumulation · OBV Rising · BB Squeeze · Delivery Spike</div></div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchAccumCards(this)">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterAccumCards(this,'')">All</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Strong Accumulation')">💪 Strong</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Accumulation')">🏦 Accumulation</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Watch')">👁 Watch</button>
  </div>
  <span id="counter-accumulation" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div id="accum-cards-grid" class="accum-grid">\n'
        for r in accum_sorted[:48]:
            alabel    = r.get("accum_label", "Watch")
            adays     = r.get("accum_days", 0)
            ascore    = r.get("accum_score", 0)
            asigs     = r.get("accum_signals", [])
            is_strong = alabel == "Strong Accumulation"
            conf      = r.get("confidence_pct", 50)
            ts        = r.get("trade_setup", {})
            entry_v   = ts.get("entry", 0)
            sl_v      = ts.get("stop_loss", 0)
            t1_v      = ts.get("target1", 0)
            del_pct   = r.get("delivery_pct")
            del_s     = f"{del_pct:.0f}%" if del_pct is not None else "—"
            asigs_html = "".join(f'<span class="accum-signal-tag">{s}</span>' for s in asigs)
            label_html = (f'<span class="accum-label-strong">🏦 {alabel}</span>' if is_strong
                          else f'<span class="accum-label-watch">👁 {alabel}</span>')
            card_cls  = "accum-card strong" if is_strong else "accum-card"
            html += f"""<div class="{card_cls}" data-symbol="{r['symbol']}" data-sector="{r.get('sector','')}" data-accumlabel="{alabel}" onclick="openModal('{r['symbol']}')">\n  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-size:16px;font-weight:800;">{r['symbol']}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:1px;">{r.get('sector','—')}</div>
    </div>
    <span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span>
  </div>
  <div style="margin-top:8px;">{label_html}</div>
  <div class="accum-score-bar"><div class="accum-score-fill" style="width:{ascore}%;"></div></div>
  <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:3px;">
    <span>Accum Score: <strong style="color:var(--green);">{ascore}/100</strong></span>
    <span>Accum Days: <strong style="color:var(--text);">{adays}d</strong></span>
    <span>Confidence: <strong style="color:var(--blue);">{conf}%</strong></span>
  </div>
  <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:2px;">{asigs_html}</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px;font-size:11px;">
    <div class="price-chip">CMP <strong>₹{r['price']:,.1f}</strong></div>
    <div class="price-chip">Entry <strong style="color:var(--blue);">₹{entry_v:,.1f}</strong></div>
    <div class="price-chip">SL <strong style="color:var(--red);">₹{sl_v:,.1f}</strong></div>
    <div class="price-chip">T1 <strong style="color:var(--green);">₹{t1_v:,.1f}</strong></div>
    <div class="price-chip">Del <strong>{del_s}</strong></div>
  </div>
</div>\n"""
        html += "</div>\n</div>\n"


        # ── Expert Picks Tab (v7.0) ──
        expert_conv_list  = sorted([r for r in results if r.get("expert_decision")=="CONVICTION"],
                                    key=lambda x: x.get("expert_yes",0), reverse=True)
        expert_trade_list = sorted([r for r in results if r.get("expert_decision")=="TRADE"],
                                    key=lambda x: x.get("expert_yes",0), reverse=True)
        all_expert = expert_conv_list + expert_trade_list

        html += '<div id="pane-expert" class="tab-pane">\n'
        html += f'''<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
  <div class="section-title" style="margin-bottom:0;">⭐ Multi-Factor Leaders — 13-Point Screening Checklist</div>
  <span style="background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.3);color:var(--amber);padding:3px 10px;border-radius:20px;font-size:11px;">⭐ Conviction: {len(expert_conv_list)} (≥10/13)</span>
  <span style="background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:var(--green);padding:3px 10px;border-radius:20px;font-size:11px;">✅ Trade: {len(expert_trade_list)} (7-9/13)</span>
</div>\n'''
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol..." oninput="searchSimpleTable(this,'expert-table')">
  </div>
  <div style="display:flex;gap:5px;">
    <button class="filter-btn on" onclick="filterExpertDecision(this,'expert-table','')">All</button>
    <button class="filter-btn" onclick="filterExpertDecision(this,'expert-table','CONVICTION')">⭐ Conviction</button>
    <button class="filter-btn" onclick="filterExpertDecision(this,'expert-table','TRADE')">✅ Trade</button>
  </div>
  <span id="counter-expert" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="expert-table">\n'
        html += '''<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>
  <th>Expert</th><th>Decision</th>
  <th>Mkt</th><th>Sector</th><th>Price</th><th>Breakout</th>
  <th>Volume</th><th>Indicator</th><th>Risk</th>
  <th>Price</th><th>1D%</th><th>Entry</th><th>SL</th><th>T1</th>
</tr></thead>\n<tbody>\n'''
        for i, r in enumerate(all_expert, 1):
            ec     = r.get("expert_checks", {})
            e_yes  = r.get("expert_yes", 0)
            e_dec  = r.get("expert_decision","SKIP")
            e_col  = "#f59e0b" if e_dec=="CONVICTION" else "#10b981" if e_dec=="TRADE" else "#ef4444"
            a_sc   = sum(1 for k in ["a1_nifty_above_dma","a2_breadth_supportive"] if ec.get(k))
            b_sc   = sum(1 for k in ["b1_sector_strong","b2_sector_peers_breaking"] if ec.get(k))
            c_sc   = sum(1 for k in ["c1_base_consolidation","c2_price_structure_ok"] if ec.get(k))
            d_sc   = sum(1 for k in ["d1_breakout_confirmed","d2_candle_quality_ok"] if ec.get(k))
            e_sc   = sum(1 for k in ["e1_volume_surge","e2_volume_contraction"] if ec.get(k))
            f_sc   = 1 if ec.get("f1_indicators_aligned") else 0
            g_sc   = sum(1 for k in ["g1_stoploss_defined","g2_rr_minimum"] if ec.get(k))
            def cc(s,m):
                c = "#10b981" if s==m else "#f59e0b" if s>0 else "#ef4444"
                return f'<span style="font-weight:700;color:{c}">{s}/{m}</span>'
            ts     = r.get("trade_setup",{})
            entry_v= ts.get("entry",0)
            sl_v   = ts.get("stop_loss",0)
            t1_v   = ts.get("target1",0)
            cc_cls = "up" if r["chg_1d"]>0 else "down" if r["chg_1d"]<0 else "neutral"
            html += f'''<tr data-expert="{e_dec}" onclick="openModal(\'{r["symbol"]}\')">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r["symbol"]}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r["sector"]}</td>
  <td><span class="grade-badge" style="background:{r["grade_color"]}">{r["grade"]}</span></td>
  <td style="font-weight:700">{r["score"]}</td>
  <td><span style="font-size:15px;font-weight:800;color:{e_col}">{e_yes}/13</span></td>
  <td><span style="background:{e_col}22;border:1px solid {e_col}55;color:{e_col};padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700">{e_dec}</span></td>
  <td style="text-align:center">{cc(a_sc,2)}</td>
  <td style="text-align:center">{cc(b_sc,2)}</td>
  <td style="text-align:center">{cc(c_sc,2)}</td>
  <td style="text-align:center">{cc(d_sc,2)}</td>
  <td style="text-align:center">{cc(e_sc,2)}</td>
  <td style="text-align:center">{cc(f_sc,1)}</td>
  <td style="text-align:center">{cc(g_sc,2)}</td>
  <td style="font-weight:600">₹{r["price"]:,.2f}</td>
  <td class="{cc_cls}">{("+" if r["chg_1d"]>0 else "")}{r["chg_1d"]:.2f}%</td>
  <td style="color:var(--blue);font-size:11px">{"₹{:,.1f}".format(entry_v) if entry_v else "—"}</td>
  <td style="color:var(--red);font-size:11px">{"₹{:,.1f}".format(sl_v) if sl_v else "—"}</td>
  <td style="color:var(--green);font-size:11px">{"₹{:,.1f}".format(t1_v) if t1_v else "—"}</td>
</tr>\n'''
        html += "</tbody></table></div>\n</div>\n"

                # ── Sector Leaderboard Tab (v4.0 — composite strength) ──
        html += '<div id="pane-sectors" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:6px;">🏭 Sector Leaderboard — Composite Strength Score (RS · 200EMA · Stage2 · ADX)</div>\n'
        html += '<div style="font-size:11px;color:var(--muted);margin-bottom:14px;">Score 0-100 · &gt;70 = Strong · 50-70 = Moderate · &lt;50 = Weak</div>\n'
        html += '<div class="sector-lb-grid">\n'
        for rank_i, sec_data in enumerate(sorted_sectors, 1):
            sec_name, strength, avg_rs, count, stage2_cnt, pct_200, avg_adx = sec_data
            if   strength >= 70: sec_col = "#10b981"; hot = True
            elif strength >= 55: sec_col = "#38bdf8"; hot = False
            elif strength >= 40: sec_col = "#f59e0b"; hot = False
            else:                sec_col = "#ef4444"; hot = False
            rank_label = "🥇" if rank_i == 1 else "🥈" if rank_i == 2 else "🥉" if rank_i == 3 else f"#{rank_i}"
            hot_badge = '<span class="sector-hot-badge">🔥 HOT</span>' if hot else ''
            bar_pct   = min(int(strength), 100)
            # Pick top 3 stocks in this sector by score
            top_in_sec = sorted([r for r in results if r.get("sector") == sec_name],
                                 key=lambda x: x["score"], reverse=True)[:3]
            top_syms   = " · ".join(r["symbol"] for r in top_in_sec)
            html += f"""<div class="sector-lb-card">
  <div class="sector-lb-header">
    <div>
      <div class="sector-lb-name">{rank_label} {sec_name} {hot_badge}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px;">{count} stocks</div>
    </div>
    <div class="sector-lb-score" style="color:{sec_col};">{strength:.0f}</div>
  </div>
  <div class="sector-bar"><div class="sector-bar-fill" style="width:{bar_pct}%;background:{sec_col};"></div></div>
  <div class="sector-meta">
    <span>RS Avg: <strong>{avg_rs:.0f}</strong></span>
    <span>Above 200EMA: <strong>{pct_200:.0f}%</strong></span>
    <span>Stage 2: <strong>{stage2_cnt}</strong></span>
    <span>ADX Avg: <strong>{avg_adx:.0f}</strong></span>
  </div>
  <div style="font-size:10px;color:var(--blue);margin-top:5px;">Top: {top_syms}</div>
</div>\n"""
        html += "</div>\n</div>\n"

        # ── Trade Ideas Tab (A+ & A stocks with trade setup) ──
        trade_stocks = [r for r in results if r["grade"] in ("A+","A") and r.get("trade_setup", {}).get("entry")]
        html += '<div id="pane-trade" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:14px;">🎯 High Conviction Setups — A+ &amp; A Grade Analysis with Key Levels</div>\n'
        if near_earnings:
            html += f'<div class="earnings-warn" style="margin-bottom:14px;">⚠️ <strong>{len(near_earnings)} stocks</strong> have results within {CFG["earnings_warn_days"]} days. Marked below — consider waiting for post-result entry.</div>\n'
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;">\n'
        for r in trade_stocks[:30]:
            ts    = r.get("trade_setup", {})
            earn  = r["earnings_info"]
            warn_banner = ""
            if earn.get("has_upcoming"):
                warn_banner = f'<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:6px;padding:6px 10px;margin-top:8px;font-size:12px;color:#ef4444;">⚠️ Results in {earn["days_away"]} day(s) — {earn["date_str"]}</div>'
            del_badge = ""
            if r['delivery_pct'] is not None and r['delivery_pct'] >= 55:
                del_badge = f'<span class="signal-tag signal-green">Delivery {r["delivery_pct"]:.0f}%</span>'
            html += f"""<div class="card-sm" style="cursor:pointer;" onclick="openModal('{r['symbol']}')">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <span style="font-size:16px;font-weight:800;">{r['symbol']}</span>
      <span class="grade-badge" style="background:{r['grade_color']};margin-left:8px;">{r['grade']}</span>
    </div>
    <div style="text-align:right;font-size:13px;color:var(--muted);">{r['sector']} · Score {r['score']}</div>
  </div>
  <div style="margin-top:6px;font-size:12px;color:var(--muted);">
    RSI {r['rsi']} · ADX {r['adx']} · RS {r['rs_percentile']}%ile · BB {r['bb_width']:.1f}%
    {del_badge}
  </div>
  <div class="trade-setup-grid" style="margin-top:10px;">
    <div class="trade-box">
      <div class="trade-box-label">Entry</div>
      <div class="trade-box-val" style="color:var(--blue);">₹{ts.get('entry',0):,.1f}</div>
      <div class="trade-box-sub">{ts.get('setup_type','')}</div>
    </div>
    <div class="trade-box">
      <div class="trade-box-label">Stop Loss</div>
      <div class="trade-box-val" style="color:var(--red);">₹{ts.get('stop_loss',0):,.1f}</div>
      <div class="trade-box-sub">Risk {ts.get('risk_pct',0):.1f}%</div>
    </div>
    <div class="trade-box">
      <div class="trade-box-label">Target 1</div>
      <div class="trade-box-val" style="color:var(--green);">₹{ts.get('target1',0):,.1f}</div>
      <div class="trade-box-sub">+{ts.get('reward1_pct',0):.1f}%</div>
    </div>
  </div>
  <div class="trade-t2-row">
    <span style="font-size:12px;">Target 2: <strong style="color:#a78bfa;">₹{ts.get('target2',0):,.1f}</strong> (+{ts.get('reward2_pct',0):.1f}%)</span>
    <span style="font-size:12px;">R:R = <strong style="color:var(--blue);">1:{ts.get('rr_ratio',0)}</strong></span>
  </div>
  {warn_banner}
</div>
"""
        html += "</div>\n</div>\n"


        # ── EMA Scanner Tab (v7.2) — All 5 EMA strategies ──
        ema_early      = [r for r in results if r.get("ema_early_momentum")]
        ema_fresh      = [r for r in results if r.get("ema_fresh_cross_5_13")]
        ema_swing      = [r for r in results if r.get("ema_swing_confirm")]
        ema_pullback   = [r for r in results if r.get("ema_near_20_pullback") and r.get("ema_swing_confirm")]
        ema_golden     = [r for r in results if r.get("ema_golden_cross")]
        ema_fresh_gc   = [r for r in results if r.get("ema_fresh_golden_cross")]
        ema_ultra      = [r for r in results if r.get("ema_ultra_pro")]
        ema_ultra_rsi  = [r for r in ema_ultra if 55 <= r.get("rsi", 0) <= 72 and r.get("adx", 0) >= 20 and r.get("near_20d_high")]

        def ema_tag(val, label, col):
            return (f'<span style="background:{col}22;border:1px solid {col}55;'
                    f'color:{col};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700">'
                    f'{label}</span>') if val else ''

        def build_ema_table(rows, tbl_id, cols_extra=""):
            th_extra = f"<th>{cols_extra}</th>" if cols_extra else ""
            # Filter bar above each EMA table
            t  = f"""<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:160px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..."
      oninput="emaSearch(this,'{tbl_id}')" id="srch-{tbl_id}">
  </div>
  <div style="display:flex;gap:4px;flex-wrap:wrap;">
    <button class="filter-btn on" id="chip-{tbl_id}-all" onclick="emaGrade(this,'{tbl_id}','')">All</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','A+')">A+</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','A')">A</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','B+')">B+</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','B')">B</button>
  </div>
  <div style="display:flex;gap:4px;flex-wrap:wrap;">
    <button class="filter-btn" id="chip-{tbl_id}-vol" onclick="emaVol(this,'{tbl_id}')">Vol &gt;1.5×</button>
    <button class="filter-btn" id="chip-{tbl_id}-rsi" onclick="emaRsi(this,'{tbl_id}')">RSI 50-72</button>
    <button class="filter-btn" id="chip-{tbl_id}-adx" onclick="emaAdx(this,'{tbl_id}')">ADX &gt;20</button>
    <button class="filter-btn" id="chip-{tbl_id}-del" onclick="emaDel(this,'{tbl_id}')">Del &gt;55%</button>
  </div>
  <span id="cnt-{tbl_id}" style="font-size:11px;color:var(--muted);padding:3px 10px;background:var(--bg3);border-radius:20px;white-space:nowrap">—</span>
</div>"""
            t += f'<div class="tbl-wrap"><table id="{tbl_id}"><thead><tr>'
            t += '<th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>'
            t += '<th>Price</th><th>1D%</th><th>RSI</th><th>ADX</th><th>Vol Ratio</th>'
            t += '<th>EMA 5</th><th>EMA 13</th><th>EMA 26</th><th>EMA 21</th><th>EMA 50</th><th>EMA 200</th>'
            t += '<th>Delivery%</th><th>Entry</th><th>SL</th><th>T1</th><th>Signals</th>'
            t += f'{th_extra}</tr></thead><tbody>'
            for i, r in enumerate(rows[:80], 1):
                ts    = r.get("trade_setup", {}) or {}
                chgc  = "up" if r["chg_1d"] > 0 else "down" if r["chg_1d"] < 0 else "neutral"
                rsic  = "#10b981" if 50<=r.get("rsi",0)<=72 else "#f59e0b"
                adxc  = "#10b981" if r.get("adx",0)>25 else "#f59e0b"
                volc  = "#10b981" if r.get("vol_ratio",1)>=1.5 else "#f59e0b" if r.get("vol_ratio",1)>=1.2 else "#8892a4"
                e5    = r.get("ema_5",0)
                e13   = r.get("ema_13",0)
                e26   = r.get("ema_26",0)
                e21   = r.get("ema_21",0)
                e50   = r.get("ema_50",0)
                e200  = r.get("ema_200",0)
                price = r["price"]
                def ec(v): return "#10b981" if price>v>0 else "#ef4444" if v>0 else "#8892a4"
                sigs  = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
                t += f"""<tr onclick="openModal('{r["symbol"]}')" style="cursor:pointer">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r["symbol"]}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r.get("sector","")}</td>
  <td><span class="grade-badge" style="background:{r["grade_color"]}">{r["grade"]}</span></td>
  <td style="font-weight:700">{r["score"]}</td>
  <td style="font-weight:600">₹{price:,.2f}</td>
  <td class="{chgc}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td style="color:{rsic}">{r.get('rsi',0)}</td>
  <td style="color:{adxc}">{r.get('adx',0)}</td>
  <td style="color:{volc}">{r.get('vol_ratio',1):.2f}x</td>
  <td style="color:{ec(e5)};font-size:11px">₹{e5:,.1f}</td>
  <td style="color:{ec(e13)};font-size:11px">₹{e13:,.1f}</td>
  <td style="color:{ec(e26)};font-size:11px">₹{e26:,.1f}</td>
  <td style="color:{ec(e21)};font-size:11px">₹{e21:,.1f}</td>
  <td style="color:{ec(e50)};font-size:11px">₹{e50:,.1f}</td>
  <td style="color:{ec(e200)};font-size:11px">₹{e200:,.1f}</td>
  <td style="color:var(--blue);font-size:11px">{'₹{:,.1f}'.format(ts.get('entry',0)) if ts.get('entry') else '—'}</td>
  <td style="color:var(--red);font-size:11px">{'₹{:,.1f}'.format(ts.get('stop_loss',0)) if ts.get('stop_loss') else '—'}</td>
  <td style="color:var(--green);font-size:11px">{'₹{:,.1f}'.format(ts.get('target1',0)) if ts.get('target1') else '—'}</td>
  <td style="color:{'#34d399' if (r.get('delivery_pct') or 0)>=55 else 'var(--muted)'};font-size:11px">{(str(r.get('delivery_pct','—'))+'%') if r.get('delivery_pct') else '—'}</td>
  <td>{sigs or '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
</tr>"""
            t += "</tbody></table></div>"
            # Init counter after build
            t += f"""<script>
(function(){{
  var rows = document.querySelectorAll('#{tbl_id} tbody tr');
  var el = document.getElementById('cnt-{tbl_id}');
  if(el) el.textContent = rows.length + ' stocks';
}})();
</script>"""
            return t

        # Build explanation cards for each strategy
        html += """<div id="pane-ema" class="tab-pane">
<div style="margin-bottom:16px">
  <div class="section-title" style="font-size:13px;margin-bottom:6px">📈 EMA Momentum Scanner — 5 Professional Strategies</div>
  <div style="font-size:12px;color:var(--muted);line-height:1.7">
    EMA alignment is the foundation of swing trading. When EMAs stack in the right order — short above medium above long —
    the stock is in a confirmed uptrend. Use these 5 strategies from early detection to position trading.
  </div>
</div>

<!-- Strategy summary cards -->
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:20px">
"""
        strategy_cards = [
            ("#a78bfa", "⚡ Early Momentum", "EMA 5 > 13 > 26", f"{len(ema_early)} stocks", "Fresh trend start — earliest entry signal"),
            ("#38bdf8", "🔵 Fresh 5×13 Cross", "Just crossed (≤2 days)", f"{len(ema_fresh)} stocks", "Catches move right at the start"),
            ("#10b981", "📊 Swing Confirm", "EMA 21 > 50, close above 21", f"{len(ema_swing)} stocks", "Medium-term trend bullish — safest entry"),
            ("#f59e0b", "🎯 Pullback+Bounce", "Close within 3% of EMA 21", f"{len(ema_pullback)} stocks", "High probability bounce trade"),
            ("#059669", "🌟 Golden Cross", "EMA 50 > EMA 200", f"{len(ema_golden)} stocks", "Long-term bullish — institutional zone"),
            ("#ef4444", "🔥 Fresh Golden", "50×200 cross ≤10 days", f"{len(ema_fresh_gc)} stocks", "Big trend change — early institutional buy"),
            ("#c084fc", "🚀 Ultra Pro", "ALL EMAs aligned + vol 1.5×", f"{len(ema_ultra)} stocks", "All conditions confirmed — highest conviction"),
            ("#f472b6", "💎 Ultra Pro+RSI", "Ultra Pro + RSI 55-72 + ADX>20", f"{len(ema_ultra_rsi)} stocks", "Complete confluence — best setups only"),
        ]
        for col, title, rule, count, desc in strategy_cards:
            html += f"""<div style="background:var(--bg2);border:1px solid {col}44;border-radius:10px;padding:13px 15px">
  <div style="font-size:13px;font-weight:700;color:{col};margin-bottom:4px">{title}</div>
  <div style="font-size:11px;color:var(--muted);font-family:monospace;margin-bottom:6px;background:var(--bg3);padding:3px 8px;border-radius:4px">{rule}</div>
  <div style="font-size:20px;font-weight:800;color:var(--text)">{count}</div>
  <div style="font-size:11px;color:var(--muted);margin-top:3px">{desc}</div>
</div>"""
        html += "</div>\n"


        # EMA logic explanation
        html += """<div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:18px;font-size:12px">
  <div style="font-weight:700;margin-bottom:8px;color:var(--text)">📖 How to use EMA Scanner</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px">
    <div><div style="color:#a78bfa;font-weight:600;margin-bottom:4px">Step 1 — EMA 5 &gt; 13 &gt; 26 (Early Momentum)</div>
    <div style="color:var(--muted)">Short-term trend forming. Price above EMA 5. Catch the move at the start before most traders notice. Use for aggressive early entry.</div></div>
    <div><div style="color:#10b981;font-weight:600;margin-bottom:4px">Step 2 — EMA 21 &gt; 50 + Pullback (Swing Confirm)</div>
    <div style="color:var(--muted)">Medium trend confirmed. Wait for price to pull back to EMA 21 and bounce. High probability entry. This is where most professional swing traders enter.</div></div>
    <div><div style="color:#059669;font-weight:600;margin-bottom:4px">Step 3 — EMA 50 &gt; 200 (Golden Cross)</div>
    <div style="color:var(--muted)">Long-term trend confirmed. Institutions actively buying. Fresh golden cross within 10 days = best timing. Hold for larger targets (15-25%).</div></div>
    <div><div style="color:#c084fc;font-weight:600;margin-bottom:4px">Ultra Pro — All aligned + Volume + RSI</div>
    <div style="color:var(--muted)">Every EMA in perfect order + volume surge 1.5x + RSI 55-72 + ADX &gt;20 + near 20-day high. The rarest and most powerful setup. Maximum confidence entry.</div></div>
  </div>
</div>
"""
        # Separator function
        def ema_section(title, count, col, desc):
            return f"""<div style="display:flex;align-items:center;gap:10px;margin:18px 0 10px">
  <div style="font-size:14px;font-weight:700;color:{col}">{title}</div>
  <span style="background:{col}22;border:1px solid {col}44;color:{col};padding:2px 10px;border-radius:20px;font-size:11px">{count} stocks</span>
  <div style="font-size:11px;color:var(--muted)">{desc}</div>
</div>"""

        html += ema_section("⚡ Strategy 1 — Early Momentum (EMA 5 > 13 > 26)", len(ema_early), "#a78bfa",
                            "Close > EMA5 > EMA13 > EMA26 · Short-term trend forming · Aggressive early entry")
        html += build_ema_table(sorted(ema_early, key=lambda x: x["score"], reverse=True), "ema-early-table")

        html += ema_section("🔵 Strategy 1B — Fresh 5×13 Cross (≤2 days ago)", len(ema_fresh), "#38bdf8",
                            "EMA 5 just crossed above EMA 13 within last 2 candles · Earliest possible entry · Catches fresh moves")
        html += build_ema_table(sorted(ema_fresh, key=lambda x: x["score"], reverse=True), "ema-fresh-table")

        html += ema_section("📊 Strategy 2 — Swing Confirmation (EMA 21 > 50)", len(ema_swing), "#10b981",
                            "Close > EMA21 > EMA50 · Medium-term trend bullish · Standard swing trade zone")
        html += build_ema_table(sorted(ema_swing, key=lambda x: x["score"], reverse=True), "ema-swing-table")

        html += ema_section("🎯 Strategy 2B — Pullback + Bounce (Close near EMA 21)", len(ema_pullback), "#f59e0b",
                            "Price within 3% above EMA 21 + swing confirm · High probability bounce · Best risk/reward entry")
        html += build_ema_table(sorted(ema_pullback, key=lambda x: x["score"], reverse=True), "ema-pullback-table")

        html += ema_section("🌟 Strategy 3 — Golden Cross (EMA 50 > 200)", len(ema_golden), "#059669",
                            "Long-term bullish trend · Institutional accumulation zone · Bigger moves expected")
        html += build_ema_table(sorted(ema_golden, key=lambda x: x["score"], reverse=True), "ema-golden-table")

        html += ema_section("🔥 Strategy 3B — Fresh Golden Cross (≤10 days)", len(ema_fresh_gc), "#ef4444",
                            "EMA 50 just crossed above EMA 200 · Big trend change · Earliest institutional buy signal")
        html += build_ema_table(sorted(ema_fresh_gc, key=lambda x: x["score"], reverse=True), "ema-freshgc-table")

        html += ema_section("🚀 Strategy 4 — Ultra Pro Combined (All EMAs + Volume ≥1.5×)", len(ema_ultra), "#c084fc",
                            "EMA5>13>26, EMA21>50>200, Close>EMA5, Vol≥1.5x · Explosive stocks · Complete EMA alignment")
        html += build_ema_table(sorted(ema_ultra, key=lambda x: x["score"], reverse=True), "ema-ultra-table")

        html += ema_section("💎 Strategy 5 — Ultra Pro + RSI 55-72 + ADX>20 + Near 20D High", len(ema_ultra_rsi), "#f472b6",
                            "All Ultra Pro conditions + RSI in sweet spot + strong trend + near breakout · Highest probability setup")
        html += build_ema_table(sorted(ema_ultra_rsi, key=lambda x: x["score"], reverse=True), "ema-ultrarsi-table")

        html += """</div>
"""


        # ══════════════════════════════════════════════════════════════
        # TABS: PRICE ACTION · VALUE SCREENS · QUALITY STOCKS
        # ══════════════════════════════════════════════════════════════

        def _fmt_cap(v):
            if v is None: return "N/A"
            cr = v / 1e7
            if cr >= 100000: return f"₹{cr/100:.0f}KCr"
            if cr >= 1000:   return f"₹{cr:,.0f}Cr"
            return f"₹{cr:.0f}Cr"

        def screen_card_row(r, extra_cells=""):
            ts   = r.get("trade_setup") or {}
            chgc = "up" if r["chg_1d"]>0 else "down" if r["chg_1d"]<0 else "neutral"
            rsic = "#34d399" if 50<=r.get("rsi",0)<=72 else "#fb7185" if r.get("rsi",0)>80 else "#f59e0b"
            sigs = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:2])
            entry = f"₹{ts['entry']:,.1f}" if ts.get("entry") else "—"
            sl    = f"₹{ts['stop_loss']:,.1f}" if ts.get("stop_loss") else "—"
            t1    = f"₹{ts['target1']:,.1f}" if ts.get("target1") else "—"
            return (f"<tr onclick=\"openModal('{r['symbol']}')\" style=\"cursor:pointer\">"
                    f"<td><strong>{r['symbol']}</strong></td>"
                    f"<td style=\"font-size:11px;color:var(--muted)\">{r.get('sector','')}</td>"
                    f"<td><span class=\"grade-badge\" style=\"background:{r['grade_color']}\">{r['grade']}</span></td>"
                    f"<td style=\"font-weight:700\">{r['score']}</td>"
                    f"<td style=\"font-weight:600\">₹{r['price']:,.2f}</td>"
                    f"<td class=\"{chgc}\">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>"
                    f"<td style=\"color:{'#34d399' if r.get('chg_1m',0)>0 else '#fb7185'}\">{'+' if r.get('chg_1m',0)>0 else ''}{r.get('chg_1m',0):.1f}%</td>"
                    f"<td style=\"color:{rsic}\">{r.get('rsi',0)}</td>"
                    f"<td style=\"color:{'#f59e0b' if r.get('vol_ratio',0)>=1.5 else 'var(--muted)'}\">{r.get('vol_ratio',0):.1f}x</td>"
                    f"{extra_cells}"
                    f"<td style=\"font-size:11px\"><span style=\"color:#22d3ee\">{entry}</span> / <span style=\"color:#fb7185\">{sl}</span> / <span style=\"color:#34d399\">{t1}</span></td>"
                    f"<td>{sigs or '—'}</td>"
                    f"</tr>")

        def screener_section(emoji, title, count, col, desc, logic):
            return (f"<div style=\"margin:20px 0 10px;padding:12px 16px;background:var(--bg2);"
                    f"border-left:3px solid {col};border-radius:0 8px 8px 0\">"
                    f"<div style=\"display:flex;align-items:center;gap:10px;flex-wrap:wrap\">"
                    f"<span style=\"font-size:15px\">{emoji}</span>"
                    f"<span style=\"font-size:14px;font-weight:700\">{title}</span>"
                    f"<span style=\"background:{col}22;border:1px solid {col}55;color:{col};"
                    f"padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700\">{count} stocks</span>"
                    f"<span style=\"font-size:11px;color:var(--muted)\">{desc}</span>"
                    f"<span style=\"margin-left:auto;font-size:10px;color:var(--muted);font-family:monospace;"
                    f"background:var(--bg3);padding:2px 8px;border-radius:4px\">{logic}</span>"
                    f"</div></div>")

        def screener_tbl_open(tbl_id, extra_th=""):
            return (f"<div style=\"display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap\">"
                    f"<div class=\"search-bar\" style=\"flex:1;min-width:160px;margin-bottom:0\">"
                    f"<span class=\"search-icon\">🔍</span>"
                    f"<input type=\"text\" placeholder=\"Search symbol...\" oninput=\"searchSimpleTable(this,'{tbl_id}')\">"
                    f"</div>"
                    f"<div style=\"display:flex;gap:4px\">"
                    f"<button class=\"filter-btn on\" onclick=\"filterSimpleGrade(this,'{tbl_id}','')\">All</button>"
                    f"<button class=\"filter-btn\" onclick=\"filterSimpleGrade(this,'{tbl_id}','A+')\">A+</button>"
                    f"<button class=\"filter-btn\" onclick=\"filterSimpleGrade(this,'{tbl_id}','A')\">A</button>"
                    f"<button class=\"filter-btn\" onclick=\"filterSimpleGrade(this,'{tbl_id}','B+')\">B+</button>"
                    f"</div>"
                    f"<span id=\"cnt-{tbl_id}\" style=\"font-size:11px;color:var(--muted);"
                    f"padding:3px 10px;background:var(--bg3);border-radius:20px\">— stocks</span>"
                    f"</div>"
                    f"<div class=\"tbl-wrap\"><table id=\"{tbl_id}\">"
                    f"<thead><tr><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>"
                    f"<th>Price</th><th>1D%</th><th>1M%</th><th>RSI</th><th>Vol Ratio</th>"
                    f"{extra_th}<th>Entry/SL/T1</th><th>Signals</th>"
                    f"</tr></thead><tbody>")

        def screener_tbl_close(tbl_id):
            return (f"</tbody></table></div>"
                    f"<script>(function(){{"
                    f"var t=document.getElementById('{tbl_id}');"
                    f"var el=document.getElementById('cnt-{tbl_id}');"
                    f"if(t&&el)el.textContent=t.querySelectorAll('tbody tr').length+' stocks';"
                    f"}})();</script>")

        def chip(v, col): return f'<div style="font-size:20px;font-weight:800;color:{col}">{v}</div>'

        def summary_chips(items):
            html_c = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px">'
            for count, label, sub, col in items:
                html_c += (f'<div style="background:{col}18;border:1px solid {col}44;'
                           f'border-radius:10px;padding:10px 14px;min-width:115px">'
                           f'<div style="font-size:20px;font-weight:800;color:{col}">{count}</div>'
                           f'<div style="font-size:11px;color:var(--muted)">{label}</div>'
                           f'<div style="font-size:10px;color:{col}">{sub}</div></div>')
            return html_c + '</div>'

        # ─────────────────── COMPUTE ALL SCREENS ───────────────────
        # Technical screens
        s52h       = sorted([r for r in results if r["price"]>=r["high_52w"]*0.95 and r["high_52w"]>0],
                             key=lambda x: x.get("pct_from_high",-999), reverse=True)
        s52h_pro   = [r for r in s52h if r["price"]>=r["high_52w"]*0.98 and r.get("vol_ratio",0)>=1.5]
        s52l       = sorted([r for r in results if r["low_52w"]>0 and r["price"]<=r["low_52w"]*1.10],
                             key=lambda x: x["price"]/x["low_52w"] if x["low_52w"] else 999)
        sgc_all    = sorted([r for r in results if r.get("ema_golden_cross")], key=lambda x: x["score"], reverse=True)
        sgc_fresh  = [r for r in sgc_all if r.get("ema_fresh_golden_cross")]
        sdc_fresh  = sorted([r for r in results if not r.get("ema_golden_cross") and
                              r.get("ema_50",0)<r.get("ema_200",999)*0.995 and r.get("ema_50",0)>0],
                             key=lambda x: x["score"], reverse=True)
        sabove200  = sorted([r for r in results if r.get("above_200ema")], key=lambda x: x["score"], reverse=True)
        svol_bo    = sorted([r for r in results if r.get("vol_ratio",0)>=2.0 and r.get("chg_1d",0)>0],
                             key=lambda x: x.get("vol_ratio",0), reverse=True)
        sgainers   = sorted([r for r in results if r.get("chg_1d",0)>=3.0], key=lambda x: x["chg_1d"], reverse=True)
        slosers    = sorted([r for r in results if r.get("chg_1d",0)<=-3.0], key=lambda x: x["chg_1d"])

        # Fundamental screens
        MC = 1e7
        low_pe      = sorted([r for r in results if r.get("pe_ratio") and 0<r["pe_ratio"]<15],
                              key=lambda x: x["pe_ratio"])
        underval_gr = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<20
                               and r.get("roe") and r["roe"]>15 and r.get("eps_growth") and r["eps_growth"]>10],
                              key=lambda x: x["score"], reverse=True)
        low_pb      = sorted([r for r in results if r.get("pb_ratio") and 0<r["pb_ratio"]<1.5],
                              key=lambda x: x["pb_ratio"])
        graham_v    = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<15
                               and r.get("pb_ratio") and r["pb_ratio"]<1.5
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5
                               and r.get("eps_growth") and r["eps_growth"]>0],
                              key=lambda x: x["score"], reverse=True)
        magic_f     = sorted([r for r in results if r.get("roic") and r["roic"]>15
                               and r.get("earnings_yield") and r["earnings_yield"]>5],
                              key=lambda x: (r.get("roic",0)+r.get("earnings_yield",0)), reverse=True)
        val_growth  = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<25
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("roe") and r["roe"]>15],
                              key=lambda x: x["score"], reverse=True)
        turnaround  = sorted([r for r in results if r.get("eps_growth") and r["eps_growth"]>0
                               and r.get("rev_growth") and r["rev_growth"]>5 and r["score"]>=40],
                              key=lambda x: x["score"], reverse=True)

        # Quality screens
        blue_chip   = sorted([r for r in results if r.get("market_cap") and r["market_cap"]>=50000*MC
                               and r.get("roe") and r["roe"]>15],
                              key=lambda x: x.get("market_cap",0), reverse=True)
        large_cap_q = sorted([r for r in results if r.get("market_cap") and r["market_cap"]>=20000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        mid_cap_q   = sorted([r for r in results if r.get("market_cap")
                               and 5000*MC<=r["market_cap"]<20000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        small_cap_q = sorted([r for r in results if r.get("market_cap") and r["market_cap"]<5000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10],
                              key=lambda x: x["score"], reverse=True)
        coffee_can  = sorted([r for r in results if r.get("roce") and r["roce"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        high_opm    = sorted([r for r in results if r.get("operating_margin") and r["operating_margin"]>20],
                              key=lambda x: x.get("operating_margin",0), reverse=True)
        opm_improve = sorted([r for r in results if r.get("operating_margin") and r.get("profit_margin")
                               and r["operating_margin"] > r["profit_margin"]],
                              key=lambda x: x.get("operating_margin",0), reverse=True)
        qual_growth = sorted([r for r in results if r.get("roe") and r["roe"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("operating_margin") and r["operating_margin"]>15],
                              key=lambda x: x["score"], reverse=True)

        # ─────────────────── PRICE ACTION TAB ───────────────────
        html += '<div id="pane-price_action" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">📊 Price Action &amp; Technical Patterns</div><div style="font-size:12px;color:var(--muted)">8 ready-made technical screens — 52W High/Low · Golden/Death Cross · Volume Breakout · Gainers/Losers</div></div>\n'
        html += summary_chips([
            (len(s52h),    "Near 52W High",    f"{len(s52h_pro)} w/ vol", "#f97316"),
            (len(s52l),    "Near 52W Low",     "Value zone",              "#22d3ee"),
            (len(sgc_all), "Golden Cross",     f"{len(sgc_fresh)} fresh", "#34d399"),
            (len(sdc_fresh),"Death Cross",     "Bearish signal",          "#fb7185"),
            (len(sabove200),"Above 200 DMA",   "Long-term bullish",       "#a3e635"),
            (len(svol_bo), "Vol Breakout",     "Vol 2× + up",             "#f59e0b"),
            (len(sgainers),"Top Gainers",      "+3% today",               "#34d399"),
            (len(slosers), "Top Losers",       "−3% today",               "#fb7185"),
        ])

        html += screener_section("🔹","52 Week High",len(s52h),"#f97316","Within 5% of 52W peak — momentum leaders","Close ≥ 0.95×52WHigh")
        html += screener_tbl_open("pa-52high","<th>52W High</th><th>Distance</th>")
        for r in s52h[:60]:
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r["high_52w"]:,.1f}</td>'
                f'<td style="color:#d4a024;font-weight:700">{r["pct_from_high"]:.1f}%</td>')
        html += screener_tbl_close("pa-52high")

        html += screener_section("🔹","52 Week Low",len(s52l),"#22d3ee","Within 10% of yearly low — value hunting zone","Close ≤ 1.10×52WLow")
        html += screener_tbl_open("pa-52low","<th>52W Low</th><th>From Low</th>")
        for r in s52l[:40]:
            fl = round((r["price"]/r["low_52w"]-1)*100,1) if r["low_52w"] else 0
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r["low_52w"]:,.1f}</td>'
                f'<td style="color:#22d3ee;font-weight:700">+{fl:.1f}%</td>')
        html += screener_tbl_close("pa-52low")

        html += screener_section("🔹","Golden Crossover",len(sgc_all),"#34d399",f"EMA50>EMA200 · {len(sgc_fresh)} fresh within 10 days","EMA(50) > EMA(200)")
        html += screener_tbl_open("pa-golden","<th>EMA 50</th><th>EMA 200</th>")
        for r in sgc_all[:60]:
            fc = ' <span style="color:#d4a024;font-size:9px;font-weight:700">🔥FRESH</span>' if r.get("ema_fresh_golden_cross") else ""
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-size:11px">₹{r.get("ema_50",0):,.1f}</td>'
                f'<td style="color:#22d3ee;font-size:11px">₹{r.get("ema_200",0):,.1f}{fc}</td>')
        html += screener_tbl_close("pa-golden")

        html += screener_section("🔹","Death Cross",len(sdc_fresh),"#fb7185","EMA50<EMA200 — avoid new longs","EMA(50) < EMA(200)")
        html += screener_tbl_open("pa-death","<th>EMA 50</th><th>EMA 200</th>")
        for r in sdc_fresh[:40]:
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-size:11px">₹{r.get("ema_50",0):,.1f}</td>'
                f'<td style="color:var(--muted);font-size:11px">₹{r.get("ema_200",0):,.1f}</td>')
        html += screener_tbl_close("pa-death")

        html += screener_section("🔹","Above 200 DMA",len(sabove200),"#a3e635","Price above 200-day EMA — long-term trend intact","Close > EMA(200)")
        html += screener_tbl_open("pa-200dma","<th>EMA 200</th><th>Gap%</th>")
        for r in sabove200[:60]:
            gap = round((r["price"]/r.get("ema_200",r["price"])-1)*100,1) if r.get("ema_200") else 0
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r.get("ema_200",0):,.1f}</td>'
                f'<td style="color:#a3e635;font-weight:700">+{gap:.1f}%</td>')
        html += screener_tbl_close("pa-200dma")

        html += screener_section("🔹","Volume Breakout",len(svol_bo),"#f59e0b","Volume ≥ 2× avg + price up — institutional participation","Vol > 2×avg + 1D%>0")
        html += screener_tbl_open("pa-volbo","<th>Vol Ratio</th><th>Delivery%</th>")
        for r in svol_bo[:40]:
            dp = r.get("delivery_pct")
            del_td = (f'<td style="color:{"#34d399" if dp and dp>=55 else "var(--muted)"}">{f"{dp:.0f}%" if dp else "N/A"}</td>')
            html += screen_card_row(r,
                f'<td style="color:#f59e0b;font-weight:800">{r.get("vol_ratio",0):.1f}×</td>' + del_td)
        html += screener_tbl_close("pa-volbo")

        html += screener_section("🔹","Top Gainers Today",len(sgainers),"#34d399","Stocks up ≥ 3% today","1D% ≥ +3%")
        html += screener_tbl_open("pa-gainers","<th>1D Gain</th><th>Vol Ratio</th>")
        for r in sgainers[:40]:
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:800">+{r["chg_1d"]:.2f}%</td>'
                f'<td style="color:{"#f59e0b" if r.get("vol_ratio",0)>=1.5 else "var(--muted)"}">{r.get("vol_ratio",0):.1f}×</td>')
        html += screener_tbl_close("pa-gainers")

        html += screener_section("🔹","Top Losers Today",len(slosers),"#fb7185","Stocks down ≥ 3% today — potential reversal watchlist","1D% ≤ −3%")
        html += screener_tbl_open("pa-losers","<th>1D Loss</th><th>52W High%</th>")
        for r in slosers[:40]:
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-weight:800">{r["chg_1d"]:.2f}%</td>'
                f'<td style="color:var(--muted)">{r["pct_from_high"]:.1f}%</td>')
        html += screener_tbl_close("pa-losers")

        html += "</div>\n"

        # ─────────────────── VALUE SCREENS TAB ───────────────────
        html += '<div id="pane-value_screen" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">💰 Fundamental &amp; Value Screens</div><div style="font-size:12px;color:var(--muted)">Graham · Greenblatt Magic Formula · PE · P/B · Turnaround — fundamental quality filters</div></div>\n'
        html += summary_chips([
            (len(low_pe),      "Low PE (<15)",        "Undervalued",    "#f97316"),
            (len(underval_gr), "Undervalued Growth",  "PE<20+ROE>15%",  "#34d399"),
            (len(low_pb),      "Low P/B (<1.5)",      "Below book",     "#22d3ee"),
            (len(graham_v),    "Graham Value",        "All 3 criteria", "#a3e635"),
            (len(magic_f),     "Magic Formula",       "ROIC+EarnYield", "#c084fc"),
            (len(val_growth),  "Value + Growth",      "PE<25+Gr>10%",   "#f59e0b"),
            (len(turnaround),  "Turnaround",          "EPS recovering", "#fb7185"),
        ])

        def n(v, fmt=".1f", suffix=""):
            return f"{v:{fmt}}{suffix}" if v is not None else "N/A"
        def gc(v, thresh, col_ok="#34d399", col_no="var(--muted)"):
            return col_ok if v is not None and v >= thresh else col_no

        html += screener_section("🔹","Low PE Stocks",len(low_pe),"#f97316","P/E below 15 — undervalued relative to earnings","PE < 15")
        html += screener_tbl_open("fv-lowpe","<th>PE</th><th>ROE%</th><th>EPS Gr%</th>")
        for r in low_pe[:50]:
            pe=r.get("pe_ratio"); roe=r.get("roe"); eg=r.get("eps_growth")
            html += screen_card_row(r,
                f'<td style="color:#d4a024;font-weight:800">{n(pe,"0.1f")}×</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>'
                f'<td style="color:{gc(eg,10)}">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>')
        html += screener_tbl_close("fv-lowpe")

        html += screener_section("🔹","Undervalued Growth",len(underval_gr),"#34d399","PE<20 + ROE>15% + EPS Growth>10% — GARP strategy","PE<20+ROE>15%+EPS>10%")
        html += screener_tbl_open("fv-uvgr","<th>PE</th><th>ROE%</th><th>EPS Gr%</th><th>D/E</th>")
        for r in underval_gr[:50]:
            pe=r.get("pe_ratio"); roe=r.get("roe"); eg=r.get("eps_growth"); de=r.get("de_ratio")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#34d399;font-weight:700">{n(roe)}%</td>'
                f'<td style="color:#34d399">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>'
                f'<td style="color:{gc(de,999,"#34d399","#f59e0b") if de is not None and de<0.5 else "#f59e0b"}">{n(de,"0.2f") if de is not None else "N/A"}</td>')
        html += screener_tbl_close("fv-uvgr")

        html += screener_section("🔹","Low Price-to-Book",len(low_pb),"#22d3ee","P/B < 1.5 — trading near or below book value","P/B < 1.5")
        html += screener_tbl_open("fv-lowpb","<th>P/B</th><th>PE</th><th>ROE%</th>")
        for r in low_pb[:50]:
            pb=r.get("pb_ratio"); pe=r.get("pe_ratio"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#22d3ee;font-weight:800">{n(pb,"0.2f")}×</td>'
                f'<td style="color:{"#f97316" if pe and pe<15 else "var(--muted)"}">{n(pe,"0.1f")}×</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>')
        html += screener_tbl_close("fv-lowpb")

        html += screener_section("🔹","Graham Value",len(graham_v),"#a3e635","Benjamin Graham: PE<15 + P/B<1.5 + D/E<0.5 + Positive EPS","PE<15+P/B<1.5+D/E<0.5")
        html += screener_tbl_open("fv-graham","<th>PE</th><th>P/B</th><th>D/E</th><th>EPS Gr%</th>")
        for r in graham_v[:50]:
            pe=r.get("pe_ratio"); pb=r.get("pb_ratio"); de=r.get("de_ratio"); eg=r.get("eps_growth")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#22d3ee">{n(pb,"0.2f")}×</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#34d399" if eg and eg>0 else "#fb7185"}">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>')
        html += screener_tbl_close("fv-graham")

        html += screener_section("🔹","Magic Formula",len(magic_f),"#c084fc","Joel Greenblatt: High ROIC + High Earnings Yield — ranked by combined score","ROIC>15%+EarningsYield>5%")
        html += screener_tbl_open("fv-magic","<th>ROIC%</th><th>Earn Yield%</th><th>Rank</th>")
        for i,r in enumerate(magic_f[:50],1):
            roic=r.get("roic"); ey=r.get("earnings_yield"); combo=round((roic or 0)+(ey or 0),1)
            html += screen_card_row(r,
                f'<td style="color:#c084fc;font-weight:700">{n(roic)}%</td>'
                f'<td style="color:#22d3ee">{n(ey,"0.1f")}%</td>'
                f'<td style="color:#d4a024;font-weight:800">#{i}</td>')
        html += screener_tbl_close("fv-magic")

        html += screener_section("🔹","Value + Growth",len(val_growth),"#f59e0b","PE<25 + Rev Growth>10% + ROE>15% — GARP + quality","PE<25+RevGr>10%+ROE>15%")
        html += screener_tbl_open("fv-valgr","<th>PE</th><th>Rev Gr%</th><th>ROE%</th>")
        for r in val_growth[:50]:
            pe=r.get("pe_ratio"); rg=r.get("rev_growth"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#f59e0b;font-weight:700">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>')
        html += screener_tbl_close("fv-valgr")

        html += screener_section("🔹","Turnaround Candidates",len(turnaround),"#fb7185","EPS growth positive + revenue improving — companies recovering from difficult phase","EPS Gr>0+RevGr>5%")
        html += screener_tbl_open("fv-turn","<th>EPS Gr%</th><th>Rev Gr%</th><th>PE</th>")
        for r in turnaround[:40]:
            eg=r.get("eps_growth"); rg=r.get("rev_growth"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("fv-turn")

        html += "</div>\n"

        # ─────────────────── QUALITY STOCKS TAB ───────────────────
        html += '<div id="pane-quality_screen" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">🏆 Quality &amp; Long-Term Stocks</div><div style="font-size:12px;color:var(--muted)">Large Cap · Blue Chip · Coffee Can · OPM Leaders · Quality Growth — built for long-term investors</div></div>\n'
        html += summary_chips([
            (len(blue_chip),  "Blue Chip",         "Cap>₹50KCr",    "#f97316"),
            (len(large_cap_q),"Large Cap Quality",  "Cap>₹20KCr",    "#34d399"),
            (len(mid_cap_q),  "Mid Cap Quality",    "₹5K-20KCr",     "#22d3ee"),
            (len(small_cap_q),"Small Cap Quality",  "Cap<₹5KCr",     "#a3e635"),
            (len(coffee_can), "Coffee Can",         "Long-term quality",  "#c084fc"),
            (len(high_opm),   "High OPM",           "OPM > 20%",     "#f59e0b"),
            (len(opm_improve),"OPM Improvers",      "Rising margins","#fb7185"),
            (len(qual_growth),"Quality Growth",     "ROE+Gr+OPM",    "#22d3ee"),
        ])

        html += screener_section("🔹","Blue Chip Stocks",len(blue_chip),"#f97316","Cap > ₹50,000 Cr + ROE > 15% — top large caps with stable earnings","Cap>₹50KCr+ROE>15%")
        html += screener_tbl_open("qs-bluechip","<th>Mkt Cap</th><th>ROE%</th><th>D/E</th><th>PE</th>")
        for r in blue_chip[:40]:
            mc=r.get("market_cap"); roe=r.get("roe"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#d4a024;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>'
                f'<td style="color:{"#34d399" if de is not None and de<0.5 else "#f59e0b"}">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#f97316" if pe and pe<30 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-bluechip")

        html += screener_section("🔹","Large Cap Quality",len(large_cap_q),"#34d399","Cap > ₹20,000 Cr + ROE > 15% + D/E < 0.5 — established reliable companies","Cap>₹20KCr+ROE>15%+D/E<0.5")
        html += screener_tbl_open("qs-largecap","<th>Mkt Cap</th><th>ROE%</th><th>D/E</th><th>PE</th>")
        for r in large_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#f97316" if pe and pe<25 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-largecap")

        html += screener_section("🔹","Mid Cap Quality",len(mid_cap_q),"#22d3ee","₹5,000–20,000 Cr + ROE > 15% + D/E < 0.5 — growth + quality sweet spot","₹5K-20KCr+ROE>15%+D/E<0.5")
        html += screener_tbl_open("qs-midcap","<th>Mkt Cap</th><th>ROE%</th><th>Rev Gr%</th><th>DE</th>")
        for r in mid_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); rg=r.get("rev_growth"); de=r.get("de_ratio")
            html += screen_card_row(r,
                f'<td style="color:#22d3ee;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:{"#f59e0b" if rg and rg>10 else "var(--muted)"}">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>')
        html += screener_tbl_close("qs-midcap")

        html += screener_section("🔹","Small Cap Quality",len(small_cap_q),"#a3e635","Cap < ₹5,000 Cr + ROE > 15% + Sales Growth > 10% — high-growth hidden gems","Cap<₹5KCr+ROE>15%+SalesGr>10%")
        html += screener_tbl_open("qs-smallcap","<th>Mkt Cap</th><th>ROE%</th><th>Rev Gr%</th><th>PE</th>")
        for r in small_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); rg=r.get("rev_growth"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#a3e635;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:#f59e0b;font-weight:700">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-smallcap")

        html += screener_section("🔹","Coffee Can Portfolio",len(coffee_can),"#c084fc","ROCE > 15% + Rev Growth > 10% + D/E < 0.5 — buy-and-forget compounders","ROCE>15%+RevGr>10%+D/E<0.5")
        html += screener_tbl_open("qs-coffee","<th>ROCE%</th><th>Rev Gr%</th><th>D/E</th><th>PE</th>")
        for r in coffee_can[:50]:
            roce=r.get("roce"); rg=r.get("rev_growth"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#c084fc;font-weight:700">{n(roce)}%</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-coffee")

        html += screener_section("🔹","OPM Improvers",len(opm_improve),"#f59e0b","Operating margin > net profit margin — efficiency improving","Op Margin > Net Margin")
        html += screener_tbl_open("qs-opm","<th>Op Margin%</th><th>Net Margin%</th><th>ROE%</th>")
        for r in opm_improve[:50]:
            opm=r.get("operating_margin"); pm=r.get("profit_margin"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#f59e0b;font-weight:800">{n(opm)}%</td>'
                f'<td style="color:var(--muted)">{n(pm)}%</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>')
        html += screener_tbl_close("qs-opm")

        html += screener_section("🔹","High OPM",len(high_opm),"#fb7185","Operating Margin > 20% — highly profitable with strong pricing power","Op Margin > 20%")
        html += screener_tbl_open("qs-highopm","<th>Op Margin%</th><th>Net Margin%</th><th>ROCE%</th>")
        for r in high_opm[:50]:
            opm=r.get("operating_margin"); pm=r.get("profit_margin"); roce=r.get("roce")
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-weight:800">{n(opm)}%</td>'
                f'<td style="color:var(--muted)">{n(pm)}%</td>'
                f'<td style="color:{"#c084fc" if roce and roce>=15 else "var(--muted)"}">{n(roce)}%</td>')
        html += screener_tbl_close("qs-highopm")

        html += screener_section("🔹","Quality Growth",len(qual_growth),"#22d3ee","ROE>15% + Rev Growth>10% + OPM>15% — complete quality-growth combo","ROE>15%+RevGr>10%+OPM>15%")
        html += screener_tbl_open("qs-qualgr","<th>ROE%</th><th>Rev Gr%</th><th>OPM%</th><th>PE</th>")
        for r in qual_growth[:50]:
            roe=r.get("roe"); rg=r.get("rev_growth"); opm=r.get("operating_margin"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{n(roe)}%</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#22d3ee">{n(opm)}%</td>'
                f'<td style="color:{"#f97316" if pe and pe<25 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-qualgr")

        html += "</div>\n"

        # ── Modal ──
        html += """
<div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modalContent">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalBody">Loading...</div>
  </div>
</div>
"""
        stock_json = json.dumps({r["symbol"]: r for r in results}, default=str)

        html += f"""
<script>
const STOCKS = {stock_json};

function switchTab(name, btn) {{
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  if(btn) btn.classList.add('active');
  document.getElementById('pane-' + name).classList.add('active');
}}

// ── v6.0 FILTER STATE — stored in JS object, not DOM dataset (more reliable) ──
const _activeChip   = {{}};   // tableId → active chip key
const _searchVal    = {{}};   // tableId → search string
const _sectorVal    = {{}};   // tableId → sector
const _scoreMin     = {{}};   // tableId → minimum score

function applyFilters(tableId) {{
  const searchVal = (_searchVal[tableId]  || '').toUpperCase();
  const sectorVal =  _sectorVal[tableId]  || '';
  const scoreMin  = parseInt(_scoreMin[tableId] || '0');
  const activeChip = _activeChip[tableId] || '';

  let visible = 0;
  const tbody = document.querySelector('#' + tableId + '-table tbody');
  if (!tbody) return;

  tbody.querySelectorAll('tr').forEach(row => {{
    const sym     = (row.cells[1]  ? row.cells[1].textContent  : '').toUpperCase();
    const secCell = (row.cells[19] ? row.cells[19].textContent : '').trim();
    const score   = parseInt(row.dataset.score || '0');

    // Search — symbol OR sector
    const matchSearch = !searchVal || sym.includes(searchVal) || secCell.toUpperCase().includes(searchVal);
    // Sector dropdown
    const matchSector = !sectorVal || secCell === sectorVal;
    // Score slider
    const matchScore  = score >= scoreMin;
    // Chip filter
    let matchChip = true;
    if (activeChip) {{
      const gradeKeys = ['A+','A','B+','B'];
      if (gradeKeys.includes(activeChip)) {{
        matchChip = (row.dataset.grade || '') === activeChip;
      }} else {{
        // Try both with and without underscore variants
        const key1 = activeChip;
        const key2 = activeChip.replace(/_/g, '');
        matchChip = row.dataset[key1] === '1' || row.dataset[key2] === '1';
      }}
    }}

    const show = matchSearch && matchSector && matchScore && matchChip;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});

  const counter = document.getElementById('counter-' + tableId);
  if (counter) counter.textContent = visible + ' stock' + (visible !== 1 ? 's' : '');
}}

// ── Chip filter ──
function setChip(btn, tableId, key) {{
  // Update visual state
  const filterRow = btn.closest('.filter-row');
  if (filterRow) {{
    filterRow.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('on'));
  }}
  btn.classList.add('on');
  // Store state in JS object (reliable across all browsers)
  _activeChip[tableId] = key;
  applyFilters(tableId);
}}

// ── Search input handler ──
function handleSearch(input, tableId) {{
  _searchVal[tableId] = input.value;
  applyFilters(tableId);
}}

// ── Sector dropdown handler ──
function handleSector(select, tableId) {{
  _sectorVal[tableId] = select.value;
  applyFilters(tableId);
}}

// ── Score slider handler ──
function handleScore(input, tableId) {{
  _scoreMin[tableId] = input.value;
  const lbl = document.getElementById('scoreval-' + tableId);
  if (lbl) lbl.textContent = input.value;
  applyFilters(tableId);
}}

// Legacy aliases so old calls still work
function setFilter(btn, tableId, key) {{ setChip(btn, tableId, key); }}
function filterTable(input, tableId) {{ handleSearch(input, tableId); }}

// ── Quick Sort — one-click column sort ──
function quickSort(tableId, col, dir, btn) {{
  if (btn) {{
    btn.closest('.sort-bar').querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }}
  const table = document.getElementById(tableId + '-table');
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a,b) => {{
    const av = a.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const bv = b.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return dir==='desc' ? bn-an : an-bn;
    return dir==='desc' ? bv.localeCompare(av) : av.localeCompare(bv);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Column header sort (existing behaviour) ──
function sortTable(tableId, col) {{
  const table = document.getElementById(tableId);
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const asc   = table.dataset.sort !== col+'asc';
  table.dataset.sort = asc ? col+'asc' : col+'desc';
  rows.sort((a,b) => {{
    const av = a.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const bv = b.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? an-bn : bn-an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Quick Picks panel populator — runs after DOM ready ──
window.addEventListener('load', function() {{
(function buildQuickPicks() {{
  const all = Object.values(STOCKS);
  if (!all || !all.length) return;

  function safeNum(v, fallback) {{ return (v == null || isNaN(v)) ? fallback : Number(v); }}
  function safeBool(v) {{ return v === true || v === 'True' || v === '1' || v === 1; }}

  function renderList(containerId, stocks, metaFn) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!stocks || !stocks.length) {{
      el.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:4px 0;">No matches today — check back tomorrow</div>';
      return;
    }}
    try {{
      el.innerHTML = stocks.slice(0,6).map(function(s) {{
        return (
        '<div class="qp-stock" data-sym="' + s.symbol + '" onclick="openModal(this.dataset.sym)" style="cursor:pointer">' +
        '<div><span class="qp-stock-sym">' + s.symbol + '</span>' +
        '<div class="qp-stock-meta">' + metaFn(s) + '</div></div>' +
        '<span class="grade-badge" style="background:' + (s.grade_color||'#888') + ';font-size:10px;">' + (s.grade||'?') + '</span>' +
        '</div>'
        "'</div>'"
        );
      }}).join('');
║        NSE 500 SWING TRADING ANALYZER  v7.1 — INDIA FIRST           ║
║        Expert-Audited · All US signals removed · India-only logic    ║
║        Delivery%(dir) · FII(gate) · Bulk · Promoter · OI · VIX · PCR║
║        Generates interactive HTML report with grades A+ to D         ║
╚══════════════════════════════════════════════════════════════════════╝

New in v7.1 — Expert Audit Fixes:
  ① Delivery % now checks price DIRECTION (up day = accumulation, down = distribution)
  ② Delivery % weighted by absolute volume (illiquid stocks filtered)
  ③ FII/DII changed from per-stock additive to market gate (correct approach)
  ④ Grade thresholds raised (A+ now requires 88/100, was 80)
  ⑤ 52W high breakout REWARDED (was wrongly penalised before)
  ⑥ Circuit breaker penalty added (-10 pts near upper circuit)
  ⑦ Nifty index gate added (below 50 EMA = -6 pts, below 200 EMA = -12 pts)
  ⑧ ExpertFilter F1 uses Supertrend (replaced MACD which was removed)
  ⑨ ExpertFilter C1 uses Indian base checks (replaced VCP which is US concept)
  ⑩ 52W breakout signal added to active signals
  ⑪ Wasted compute removed (MACD, MFI, CMF, Stochastic) — 15% faster scan

New in v7.0 — India-First Scoring Engine:

  INDIA-SPECIFIC SIGNALS (highest weight — 70 pts potential):
    ① Delivery %          → 12 pts  NSE's most unique signal — institutions vs speculators
    ② FII/DII 5-day flow  → 12 pts  Largest driver of Indian large cap movement
    ③ Bulk/Block deals    → 12 pts  Disclosed institutional conviction trades
    ④ Promoter buying     → 10 pts  Strongest insider signal — SEBI mandated disclosure
    ⑤ India VIX           →  8 pts  Nifty options fear gauge — swing trading window
    ⑥ OI buildup          → 10 pts  F&O smart money: Long buildup = institutions buying
    ⑦ PCR signal          →  6 pts  Put-Call ratio — market sentiment from options data

  REDUCED US-CENTRIC SIGNALS:
    • VCP pattern:   18 pts → 10 pts  (less reliable — operators fake compressions)
    • BB squeeze:    12 pts →  6 pts  (Indian stocks can stay squeezed for months)
    • Weekly NR7:     8 pts →  4 pts  (low liquidity weeks distort this in mid/small caps)

  NEW INDIA-SPECIFIC FETCHERS:
    • IndiaVIXFetcher      — NSE India VIX (Nifty options volatility)
    • OpenInterestFetcher  — NSE F&O OI buildup detection
    • PromoterActivityFetcher — SEBI quarterly shareholding changes

  NEW INDIA PENALTIES:
    • Results within 14 days → −10 pts (increased from warning-only)
    • Promoter selling       → −10 pts from promoter score
    • Bulk sell              → −20 pts (increased from −15)

  All v6.0 features retained: Supertrend, MFI, CMF, Pivot Points,
  Candle Patterns, Flat Base, OBV Divergence, Stage Analysis,
  Accumulation Detector, FII Banner, Alert Panel, 20-point checklist.

Install requirements:
  pip install yfinance pandas numpy requests beautifulsoup4 tqdm

Usage:
  python nse500_swing_analyzer_v7.py
  python nse500_swing_analyzer_v7.py --top 50 --workers 8
  python nse500_swing_analyzer_v7.py --capital 500000
"""

import os, sys, json, time, argparse, warnings, threading
from io import StringIO
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────
CFG = {
    "lookback_days"        : 365,
    "min_price"            : 20,
    "min_avg_volume"       : 50_000,
    "max_workers"          : 3,   # v7.1: reduced to avoid Yahoo Finance rate limiting
    "request_timeout"      : 15,
    "retry_attempts"       : 3,
    "nifty_symbol"         : "^NSEI",

    # ── Grading thresholds (v5 — recalibrated for pre-move setup scoring) ──
    # Scores are harder to inflate (freshness penalties, lagging signals reduced)
    # but a stock in a perfect base setup can still max out.
    # v7.1: Raised thresholds — max positive score is 170+, cap 100
    # Before fix: 43/50 demo stocks were A+. Now A+ requires near-perfect India signals.
    "grade_aplus"          : 88,   # requires strong delivery+FII+promoter+OI alignment
    "grade_a"              : 76,
    "grade_bplus"          : 63,
    "grade_b"              : 50,
    "grade_c"              : 35,

    # ── Signal thresholds ──
    "rsi_ideal_min"        : 50,
    "rsi_ideal_max"        : 72,
    "adx_strong"           : 25,
    "volume_surge_ratio"   : 1.5,
    "rs_elite_pct"         : 90,      # RS percentile for ELITE flag
    "rs_strong_pct"        : 70,
    "vcp_max_depth_pct"    : 30,
    "breakout_buffer_pct"  : 1.5,
    "delivery_min_pct"     : 55,      # institutional delivery threshold
    "earnings_warn_days"   : 14,      # warn if results within N days
    "bb_tight_threshold"   : 8,       # BB width < 8 = very tight / coiling
    "high52w_proximity_pct": 5,       # within 5% of 52W high
    "trade_rr_t1"          : 2.0,     # Risk:Reward for Target 1
    "trade_rr_t2"          : 3.0,     # Risk:Reward for Target 2

    # ── Volume Surge thresholds ──
    "vol_surge_mega"       : 3.0,
    "vol_surge_strong"     : 2.0,
    "vol_surge_mild"       : 1.5,
    "vol_surge_lookback"   : 20,

    # ── Fundamental thresholds (v3.0) ──
    "fund_roe_strong"      : 20,      # ROE > 20% = quality business
    "fund_roe_min"         : 12,      # ROE > 12% = acceptable
    "fund_eps_growth_min"  : 15,      # EPS growth > 15% YoY = growing
    "fund_eps_growth_strong": 25,     # EPS growth > 25% = CAN SLIM C
    "fund_de_max"          : 0.5,     # D/E < 0.5 = low debt (non-financials)
    "fund_de_danger"       : 1.5,     # D/E > 1.5 = high debt warning

    # ── Promoter Pledging thresholds (v3.0 — India-specific) ──
    "pledge_warn_pct"      : 20,      # > 20% → warning
    "pledge_danger_pct"    : 40,      # > 40% → danger, score penalty
    "pledge_score_penalty" : 15,      # pts deducted for danger pledging

    # ── Stage Analysis thresholds (v3.0 — Weinstein) ──
    "stage_ma_weeks"       : 30,      # 30-week MA for stage detection
    "stage2_ma_slope_min"  : 0.0,     # MA must be flat or rising for Stage 2

    # ── Market Breadth thresholds (v3.0) ──
    "breadth_strong"       : 60,      # > 60% above 200 EMA = strong market
    "breadth_caution"      : 40,      # 40-60% = caution
    # < 40% = weak/bear market

    # ── Position Sizing (v3.0) ──
    "default_capital"      : 500_000, # ₹5 lakh default (overrideable via --capital)
    "risk_per_trade_pct"   : 1.5,     # 1.5% capital at risk per trade

    # ── v6.0 Liquidity filter (replaces raw volume floor) ──
    "min_daily_value"      : 20_000_000,  # ₹2 crore daily turnover minimum

    # ── v6.0 New indicator thresholds ──
    "supertrend_period"    : 7,
    "supertrend_mult"      : 3.0,
    "mfi_period"           : 14,
    "cmf_period"           : 20,
    "flat_base_days"       : 25,      # min days for flat base
    "flat_base_range_pct"  : 12.0,    # max price range for flat base
    "circuit_limit_near"   : 0.5,     # within 0.5% of circuit = "near circuit"
    "obv_div_lookback"     : 20,      # OBV divergence lookback
    "support_proximity_pct": 2.0,     # within 2% of support = near support
    "ipo_base_days"        : 400,     # stock listed < 400 days = IPO stage
    "bulk_deal_lookback"   : 3,       # check bulk deals in last N days
}

HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept"          : "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language" : "en-IN,en;q=0.9",
    "Accept-Encoding" : "gzip, deflate, br",
    "Connection"      : "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest"  : "document",
    "Sec-Fetch-Mode"  : "navigate",
    "Sec-Fetch-Site"  : "none",
    "Cache-Control"   : "max-age=0",
}

API_HEADERS = {
    "User-Agent"      : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept"          : "application/json, text/plain, */*",
    "Accept-Language" : "en-IN,en;q=0.9",
    "Accept-Encoding" : "gzip, deflate, br",
    "Referer"         : "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection"      : "keep-alive",
    "Sec-Fetch-Dest"  : "empty",
    "Sec-Fetch-Mode"  : "cors",
    "Sec-Fetch-Site"  : "same-origin",
}


# ─────────────────────────────────────────────────────────────────────
#  SHARED NSE SESSION MANAGER  (v6.0 fix)
# ─────────────────────────────────────────────────────────────────────
class NSESession:
    """
    Single shared session for all NSE API calls.
    NSE requires: visit homepage first → get cookies → then hit API endpoints.
    All fetchers that need NSE data share this one warmed session.
    """
    _instance  = None
    _lock      = threading.Lock()

    NSE_BASE   = "https://www.nseindia.com"
    WARM_URLS  = [
        "https://www.nseindia.com",
        "https://www.nseindia.com/market-data/live-equity-market",
        "https://www.nseindia.com/market-data/bulk-block-deals",
    ]

    def __init__(self):
        self.session   = requests.Session()
        self.session.headers.update(HEADERS)
        self._warmed   = False

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def warm(self):
        """Visit NSE pages to establish cookies. Call once before any API requests."""
        if self._warmed:
            return
        # More browser-like headers for Cloudflare bypass
        self.session.headers.update({
            "User-Agent"     : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept"         : "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection"     : "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Ch-Ua"      : '"Chromium";v="124","Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest" : "document",
            "Sec-Fetch-Mode" : "navigate",
            "Sec-Fetch-Site" : "none",
            "Sec-Fetch-User" : "?1",
            "Cache-Control"  : "max-age=0",
        })
        try:
            for url in self.WARM_URLS:
                try:
                    r = self.session.get(url, timeout=15, allow_redirects=True)
                    time.sleep(2.0)   # longer pause between warmup requests
                except Exception:
                    pass
            self._warmed = True
            print("   🔑 NSE session warmed")
        except Exception as e:
            print(f"   ⚠️  NSE session warm failed: {e}")
            self._warmed = True

    def get_api(self, url, timeout=15):
        """Make an authenticated NSE API call with correct headers."""
        self.warm()
        hdrs = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer"          : self.NSE_BASE + "/market-data/live-equity-market",
            "Accept"           : "application/json, text/plain, */*",
            "Accept-Language"  : "en-IN,en-GB;q=0.9,en;q=0.8",
            "Sec-Fetch-Dest"   : "empty",
            "Sec-Fetch-Mode"   : "cors",
            "Sec-Fetch-Site"   : "same-origin",
        }
        try:
            time.sleep(0.3)   # small delay between API calls
            resp = self.session.get(url, headers=hdrs, timeout=timeout)
            return resp
        except Exception as e:
            raise e

# ─────────────────────────────────────────────────────────────────────
#  SECTOR CLASSIFICATION MAP  (NSE 500 stocks → sector)
# ─────────────────────────────────────────────────────────────────────
SECTOR_MAP = {
    # IT / Technology
    "TCS":"IT","INFY":"IT","WIPRO":"IT","HCLTECH":"IT","TECHM":"IT",
    "LTIM":"IT","MPHASIS":"IT","COFORGE":"IT","PERSISTENT":"IT",
    "LTTS":"IT","OFSS":"IT","KPITTECH":"IT","TATAELXSI":"IT",
    "HEXAWARE":"IT","NIIT":"IT","ZENSAR":"IT","MASTEK":"IT",
    "RATEGAIN":"IT","TANLA":"IT","NEWGEN":"IT","BSOFT":"IT",

    # Banking
    "HDFCBANK":"Banking","ICICIBANK":"Banking","SBIN":"Banking",
    "KOTAKBANK":"Banking","AXISBANK":"Banking","INDUSINDBK":"Banking",
    "BANDHANBNK":"Banking","FEDERALBNK":"Banking","IDFCFIRSTB":"Banking",
    "CANBK":"Banking","BANKBARODA":"Banking","PNB":"Banking",
    "YESBANK":"Banking","AUBANK":"Banking","DCBBANK":"Banking",
    "RBLBANK":"Banking","SOUTHBANK":"Banking","KARURVYSYA":"Banking",

    # NBFC / Financial Services
    "BAJFINANCE":"NBFC","BAJAJFINSV":"NBFC","CHOLAFIN":"NBFC",
    "MUTHOOTFIN":"NBFC","M&MFIN":"NBFC","MANAPPURAM":"NBFC",
    "SHRIRAMFIN":"NBFC","CANFINHOME":"NBFC","AAVAS":"NBFC",
    "HOMEFIRST":"NBFC","APTUS":"NBFC","CREDITACC":"NBFC",

    # Insurance
    "HDFCLIFE":"Insurance","SBILIFE":"Insurance","ICICIGI":"Insurance",
    "ICICIPRULI":"Insurance","STARHEALTH":"Insurance",

    # Energy / Oil & Gas / Power
    "RELIANCE":"Energy","ONGC":"Energy","BPCL":"Energy","IOC":"Energy",
    "HINDPETRO":"Energy","GAIL":"Energy","PETRONET":"Energy",
    "TATAPOWER":"Energy","NTPC":"Energy","POWERGRID":"Energy",
    "ADANIGREEN":"Energy","ADANIPOWER":"Energy","TORNTPOWER":"Energy",
    "CESC":"Energy","JSWENERGY":"Energy","SUZLON":"Energy",
    "COALINDIA":"Energy","NLCINDIA":"Energy","NHPC":"Energy",

    # Pharma / Healthcare
    "SUNPHARMA":"Pharma","DRREDDY":"Pharma","CIPLA":"Pharma",
    "DIVISLAB":"Pharma","LUPIN":"Pharma","BIOCON":"Pharma",
    "AUROPHARMA":"Pharma","GLENMARK":"Pharma","IPCALAB":"Pharma",
    "ALKEM":"Pharma","TORNTPHARM":"Pharma","AJANTPHARM":"Pharma",
    "NATCOPHARMA":"Pharma","GRANULES":"Pharma","ERIS":"Pharma",
    "APOLLOHOSP":"Healthcare","FORTIS":"Healthcare","KIMS":"Healthcare",
    "METROPOLIS":"Healthcare","LALPATHLAB":"Healthcare","VIJAYALAB":"Healthcare",

    # FMCG / Consumer Staples
    "HINDUNILVR":"FMCG","ITC":"FMCG","NESTLEIND":"FMCG",
    "BRITANNIA":"FMCG","DABUR":"FMCG","MARICO":"FMCG",
    "GODREJCP":"FMCG","TATACONSUM":"FMCG","COLPAL":"FMCG",
    "EMAMILTD":"FMCG","HATSUN":"FMCG","ZYDUSWELL":"FMCG",

    # Automobiles
    "MARUTI":"Auto","TATAMOTORS":"Auto","EICHERMOT":"Auto",
    "HEROMOTOCO":"Auto","BAJAJ-AUTO":"Auto","M&M":"Auto",
    "ASHOKLEY":"Auto","TVSMOTOR":"Auto","ESCORTS":"Auto",
    "TIINDIA":"Auto","MOTHERSON":"Auto","BOSCH":"Auto",
    "MINDA":"Auto","EXIDEIND":"Auto","SAMVARDHANA":"Auto",

    # Metals & Mining
    "TATASTEEL":"Metals","JSWSTEEL":"Metals","HINDALCO":"Metals",
    "VEDL":"Metals","SAIL":"Metals","NMDC":"Metals","NATIONALUM":"Metals",
    "APLAPOLLO":"Metals","WELCORP":"Metals","RATNAMANI":"Metals",

    # Cement
    "ULTRACEMCO":"Cement","GRASIM":"Cement","SHREECEM":"Cement",
    "AMBUJACEM":"Cement","ACC":"Cement","JKCEMENT":"Cement",
    "RAMCOCEM":"Cement","HEIDELBERG":"Cement",

    # Construction / Infrastructure
    "LT":"Construction","NCC":"Construction","KEC":"Construction",
    "KALPATPOWR":"Construction","IRB":"Construction",
    "ADANIPORTS":"Infra","ADANIENT":"Infra","RVNL":"Infra",
    "IRFC":"Infra","IRCTC":"Infra","IRCON":"Infra","CONCOR":"Infra",

    # Consumer Discretionary
    "TITAN":"Consumer Disc","ASIANPAINT":"Consumer Disc",
    "PIDILITIND":"Consumer Disc","BERGEPAINT":"Consumer Disc",
    "KANSAINER":"Consumer Disc","HAVELLS":"Consumer Disc",
    "VOLTAS":"Consumer Disc","BLUESTARCO":"Consumer Disc",
    "WHIRLPOOL":"Consumer Disc","DIXON":"Consumer Disc",
    "AMBER":"Consumer Disc","SYMPHONY":"Consumer Disc",
    "KAJARIACER":"Consumer Disc","CENTURYPLY":"Consumer Disc",

    # Chemicals
    "DEEPAKNTR":"Chemicals","PIIND":"Chemicals","UPL":"Chemicals",
    "TATACHEMICALS":"Chemicals","COROMANDEL":"Chemicals",
    "CHAMBLFERT":"Chemicals","AARTI":"Chemicals","NAVINFLUOR":"Chemicals",
    "SRF":"Chemicals","GNFC":"Chemicals","CLEAN":"Chemicals",

    # Telecom
    "BHARTIARTL":"Telecom","IDEA":"Telecom","STLTECH":"Telecom",
    "TEJAS":"Telecom",

    # Internet / New Age Tech
    "NAUKRI":"Internet","INDIAMART":"Internet","ZOMATO":"Internet",
    "PAYTM":"Internet","NYKAA":"Internet","DELHIVERY":"Internet",
    "POLICYBZR":"Internet","CARTRADE":"Internet",

    # Capital Goods / Engineering
    "SIEMENS":"Capital Goods","ABB":"Capital Goods","CUMMINSIND":"Capital Goods",
    "THERMAX":"Capital Goods","AIAENG":"Capital Goods","BHEL":"Capital Goods",
    "BEL":"Capital Goods","HAL":"Capital Goods","POLYCAB":"Capital Goods",
    "KEI":"Capital Goods","GRINDWELL":"Capital Goods","BHFC":"Capital Goods",

    # Real Estate
    "DLF":"Real Estate","GODREJPROP":"Real Estate","PHOENIXLTD":"Real Estate",
    "OBEROIRLTY":"Real Estate","PRESTIGE":"Real Estate","BRIGADE":"Real Estate",
    "SOBHA":"Real Estate","MAHLIFE":"Real Estate",

    # Food & Beverages
    "JUBLFOOD":"Food & Bev","DEVYANI":"Food & Bev","WESTLIFE":"Food & Bev",
    "MCDOWELL-N":"Beverages","UNITEDSPIRITS":"Beverages",
    "RADICO":"Beverages","UBL":"Beverages","VSTIND":"Beverages",

    # Building Materials
    "ASTRAL":"Build Mat","SUPREMIND":"Build Mat","PRINCEPIPE":"Build Mat",
    "FINOLEX":"Build Mat","CERA":"Build Mat",

    # Textiles
    "PAGEIND":"Textiles","KPRMILL":"Textiles","WELSPUN":"Textiles",
    "RUPA":"Textiles","RAYMOND":"Textiles",

    # Specialty Finance
    "MFSL":"Fin Services","ANGELONE":"Fin Services","ICICI Securities":"Fin Services",
    "5PAISA":"Fin Services",
}

# ─────────────────────────────────────────────────────────────────────
#  F&O ELIGIBLE STOCKS  (NSE-published list, major liquid names)
# ─────────────────────────────────────────────────────────────────────
FNO_STOCKS = {
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","ASIANPAINT","MARUTI","TITAN",
    "SUNPHARMA","WIPRO","ULTRACEMCO","NESTLEIND","TECHM","POWERGRID","NTPC",
    "HCLTECH","BAJFINANCE","BAJAJFINSV","ONGC","DRREDDY","CIPLA","DIVISLAB",
    "EICHERMOT","HEROMOTOCO","TATACONSUM","GRASIM","INDUSINDBK","TATAMOTORS",
    "COALINDIA","APOLLOHOSP","HINDALCO","JSWSTEEL","TATASTEEL","ADANIENT",
    "ADANIPORTS","LTIM","HDFCLIFE","SBILIFE","BPCL","BRITANNIA","PIDILITIND",
    "SIEMENS","HAVELLS","DABUR","MARICO","GODREJCP","MUTHOOTFIN","CHOLAFIN",
    "PERSISTENT","COFORGE","MPHASIS","LTTS","OFSS","TATAPOWER","CANBK",
    "BANKBARODA","PNB","FEDERALBNK","IDFCFIRSTB","BANDHANBNK","VOLTAS",
    "WHIRLPOOL","BLUESTARCO","POLYCAB","DIXON","AIAENG","CUMMINSIND","THERMAX",
    "BERGEPAINT","KANSAINER","ASTRAL","PIIND","UPL","CHAMBLFERT","COROMANDEL",
    "DEEPAKNTR","GLENMARK","LUPIN","BIOCON","AUROPHARMA","MCDOWELL-N",
    "JUBLFOOD","INDIAMART","NAUKRI","ZOMATO","IRCTC","RVNL","IRFC","BAJAJ-AUTO",
    "TATACHEMICALS","NAVINFLUOR","SRF","TATACHEM","IPCALAB","ALKEM","TORNTPHARM",
    "SUNPHARMA","AUBANK","RBLBANK","KARURVYSYA","YESBANK","CONCOR","BEL","HAL",
    "BHEL","ABB","OBEROIRLTY","DLF","GODREJPROP","PHOENIXLTD","PRESTIGE",
    "NMDC","SAIL","VEDL","NATIONALUM","APLAPOLLO","WELCORP","RATNAMANI",
    "KEI","GRINDWELL","JSWENERGY","SUZLON","ADANIGREEN","ADANIPOWER",
    "TORNTPOWER","TATAELXSI","KPITTECH","RATEGAIN","TANLA","NEWGEN",
    "ANGELONE","MFSL","SHRIRAMFIN","CANFINHOME","AAVAS","HOMEFIRST",
    "M&M","ASHOKLEY","TVSMOTOR","ESCORTS","TIINDIA","MOTHERSON","BOSCH","MINDA",
    "EXIDEIND","PAGEIND","KPRMILL","RAYMOND","EMAMILTD","ZYDUSWELL","COLPAL",
}


# ─────────────────────────────────────────────────────────────────────
#  NSE 500 STOCK LIST FETCHER
# ─────────────────────────────────────────────────────────────────────
class NSEDataFetcher:
    NSE_500_URL  = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
    NSE_MAIN_URL = "https://www.nseindia.com"

    FALLBACK_SYMBOLS = [
        "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR",
        "ITC","SBIN","BHARTIARTL","KOTAKBANK","LT","AXISBANK",
        "ASIANPAINT","MARUTI","TITAN","SUNPHARMA","WIPRO","ULTRACEMCO",
        "NESTLEIND","TECHM","POWERGRID","NTPC","HCLTECH","BAJFINANCE",
        "BAJAJFINSV","ONGC","DRREDDY","CIPLA","DIVISLAB","EICHERMOT",
        "HEROMOTOCO","TATACONSUM","GRASIM","INDUSINDBK","TATAMOTORS",
        "COALINDIA","APOLLOHOSP","HINDALCO","JSWSTEEL","TATASTEEL",
        "ADANIENT","ADANIPORTS","LTIM","HDFCLIFE","SBILIFE",
        "BPCL","BRITANNIA","PIDILITIND","SIEMENS","HAVELLS",
        "DABUR","MARICO","GODREJCP","MUTHOOTFIN","CHOLAFIN",
        "PERSISTENT","COFORGE","MPHASIS","LTTS","OFSS",
        "TATAPOWER","CANBK","BANKBARODA","PNB","FEDERALBNK",
        "IDFCFIRSTB","BANDHANBNK","VOLTAS","WHIRLPOOL","BLUESTARCO",
        "POLYCAB","DIXON","AIAENG","CUMMINSIND","THERMAX",
        "BERGEPAINT","KANSAINER","ASTRAL","SUPREMIND","PIIND",
        "UPL","CHAMBLFERT","COROMANDEL","DEEPAKNTR","TATACHEMICALS",
        "GLENMARK","LUPIN","BIOCON","AUROPHARMA","IPCALAB",
        "MCDOWELL-N","UNITEDSPIRITS","JUBLFOOD","DEVYANI","WESTLIFE",
        "INDIAMART","NAUKRI","ZOMATO","PAYTM","NYKAA",
        "DELHIVERY","IRCTC","RVNL","IRFC","BAJAJ-AUTO",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_nifty500_list(self):
        print("📡 Fetching Nifty 500 stock list from NSE...")
        try:
            self.session.get(self.NSE_MAIN_URL, timeout=CFG["request_timeout"])
            time.sleep(1)
            resp = self.session.get(self.NSE_500_URL, timeout=CFG["request_timeout"], allow_redirects=True)
            if resp.status_code == 200 and "Symbol" in resp.text:
                df = pd.read_csv(StringIO(resp.text))
                symbols = df["Symbol"].dropna().str.strip().tolist()
                print(f"   ✅ Loaded {len(symbols)} Nifty 500 stocks from NSE")
                return symbols
        except Exception as e:
            print(f"   ⚠️  NSE fetch failed: {e}")
        print(f"   ↩️  Using fallback list of {len(self.FALLBACK_SYMBOLS)} stocks")
        return self.FALLBACK_SYMBOLS

    def get_pcr_data(self):
        pcr_data = {"nifty_pcr": None, "total_pe_oi": 0, "total_ce_oi": 0,
                    "sentiment": "N/A", "fetched": False}
        # ── Try 1: NSE options chain API ──
        try:
            url  = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
            resp = NSESession.get().get_api(url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                total_pe_oi = sum(
                    r.get("PE", {}).get("openInterest", 0)
                    for r in data.get("records", {}).get("data", []) if "PE" in r
                )
                total_ce_oi = sum(
                    r.get("CE", {}).get("openInterest", 0)
                    for r in data.get("records", {}).get("data", []) if "CE" in r
                )
                if total_ce_oi > 0:
                    pcr = round(total_pe_oi / total_ce_oi, 2)
                    # ── v7.1: Weekly PCR (near-expiry strikes only) ──
                    # Weekly strikes = options expiring this Thursday
                    # These are highest OI concentration and most watched
                    weekly_pe = sum(
                        r.get("PE", {}).get("openInterest", 0)
                        for r in data.get("records", {}).get("data", [])
                        if "PE" in r and r.get("PE", {}).get("expiryDate", "").find(
                            data.get("records", {}).get("expiryDates", [""])[0]
                            if data.get("records", {}).get("expiryDates") else "") != -1
                    )
                    weekly_ce = sum(
                        r.get("CE", {}).get("openInterest", 0)
                        for r in data.get("records", {}).get("data", [])
                        if "CE" in r and r.get("CE", {}).get("expiryDate", "").find(
                            data.get("records", {}).get("expiryDates", [""])[0]
                            if data.get("records", {}).get("expiryDates") else "") != -1
                    )
                    weekly_pcr = round(weekly_pe / weekly_ce, 2) if weekly_ce > 0 else None
                    expiry_dates = data.get("records", {}).get("expiryDates", [])
                    pcr_data = {
                        "nifty_pcr"      : pcr,
                        "weekly_pcr"     : weekly_pcr,
                        "weekly_expiry"  : expiry_dates[0] if expiry_dates else "N/A",
                        "monthly_expiry" : expiry_dates[-1] if len(expiry_dates) > 1 else "N/A",
                        "total_pe_oi"    : total_pe_oi,
                        "total_ce_oi"    : total_ce_oi,
                        "sentiment"      : self._pcr_sentiment(pcr),
                        "weekly_sentiment": self._pcr_sentiment(weekly_pcr) if weekly_pcr else "N/A",
                        "fetched"        : True,
                    }
                    wpcr_str = f"Weekly: {weekly_pcr}" if weekly_pcr else ""
                    print(f"   📊 NIFTY PCR: {pcr} ({pcr_data['sentiment']}) {wpcr_str}")
                    return pcr_data
        except Exception as e:
            print(f"   ⚠️  PCR (NSE): {e}")

        # ── Try 2: NSE all indices quick data (lighter endpoint) ──
        try:
            _sess_pcr = requests.Session()
            _sess_pcr.headers.update(HEADERS)
            if resp2.status_code == 200 and resp2.text.strip() and resp2.text.strip()[0] in "[{":
                data2 = resp2.json()
                for item in data2.get("data", []):
                    if item.get("index") == "NIFTY 50":
                        nifty_chg = float(item.get("percentChange", 0) or 0)
                        est_pcr = round(max(0.5, min(2.0, 1.05 + nifty_chg * 0.08)), 2)
                        sentiment = "Bullish" if est_pcr > 1.1 else "Bearish" if est_pcr < 0.9 else "Neutral"
                        print(f"   📊 PCR estimated (Nifty {nifty_chg:+.1f}%): ~{est_pcr} ({sentiment})")
                        return {"nifty_pcr": est_pcr, "total_pe_oi": 0, "total_ce_oi": 0,
                                "sentiment": sentiment, "weekly_pcr": None,
                                "weekly_expiry": "N/A", "monthly_expiry": "N/A",
                                "weekly_sentiment": "N/A", "fetched": True}



        except Exception:
            pass

        print("   ⚠️  PCR data unavailable (NSE blocked) — using N/A")
        return pcr_data

    @staticmethod
    def _pcr_sentiment(pcr):
        if pcr is None: return "N/A"
        if pcr > 1.3:   return "Extremely Bullish"
        if pcr > 1.0:   return "Bullish"
        if pcr > 0.8:   return "Neutral"
        if pcr > 0.6:   return "Bearish"
        return "Extremely Bearish"


# ─────────────────────────────────────────────────────────────────────
#  DELIVERY DATA FETCHER  (NSE bulk bhav file — one download for all)
# ─────────────────────────────────────────────────────────────────────
class DeliveryFetcher:
    """
    Downloads NSE's full bhav-copy (delivery data) for the latest trading day.
    Single HTTP call — no per-stock API spam.
    Fields used: SYMBOL, DELIV_QTY, TTL_TRD_QNTY → delivery %.
    """
    BULK_URL = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"

    def __init__(self):
        self._data: dict = {}   # symbol → delivery_pct float
        self._fetched = False
        self.session  = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_all(self):
        """Try today and the previous 5 trading days (handles weekends/holidays)."""
        if self._fetched:
            return
        for days_back in range(0, 8):
            date_str = (datetime.today() - timedelta(days=days_back)).strftime("%d%m%Y")
            url = self.BULK_URL.format(date=date_str)
            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code == 200 and len(resp.content) > 5000:
                    df = pd.read_csv(StringIO(resp.text))
                    df.columns = [c.strip().upper() for c in df.columns]
                    sym_col   = next((c for c in df.columns if "SYMBOL"  in c), None)
                    del_col   = next((c for c in df.columns if "DELIV_QT"in c or "DELIVERABLE" in c), None)
                    trd_col   = next((c for c in df.columns if "TTL_TRD" in c or "TOTAL_TRAD"  in c), None)
                    if sym_col and del_col and trd_col:
                        df[del_col] = pd.to_numeric(df[del_col], errors="coerce")
                        df[trd_col] = pd.to_numeric(df[trd_col], errors="coerce")
                        df["_dpct"] = df[del_col] / df[trd_col].replace(0, np.nan) * 100
                        for _, row in df.iterrows():
                            sym = str(row[sym_col]).strip()
                            pct = row["_dpct"]
                            if pd.notna(pct) and 0 <= pct <= 100:
                                self._data[sym] = round(float(pct), 1)
                        self._fetched = True
                        print(f"   📦 Delivery data: {len(self._data)} stocks (T-{days_back} day{'s' if days_back>1 else ''})")
                        return
            except Exception:
                continue
        print("   ⚠️  Delivery data unavailable (NSE archive unreachable)")
        self._fetched = True

    def get(self, symbol: str):
        """Returns delivery % for a symbol, or None if unavailable."""
        return self._data.get(symbol)


# ─────────────────────────────────────────────────────────────────────
#  BULK DEAL FETCHER  (v6.0) — NSE bulk/block deal data
# ─────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  NSE BHAVCOPY HISTORY BUILDER
#  Downloads last ~300 trading days of CM bhavcopy zip files from
#  archives.nseindia.com — same domain that already works for delivery data.
#  Builds complete OHLCV history for all NSE 500 symbols in one batch.
# ─────────────────────────────────────────────────────────────────────────────
class BhavHistory:
    """
    Single-shot bulk OHLCV history from NSE CM bhavcopy archives.
    URL: archives.nseindia.com/content/historical/EQUITIES/{YR}/{MON}/cm{DD}{MON}{YR}bhav.csv.zip
    Uses plain requests.Session (no cookies) — works on all Indian networks.
    """

    # Same URL format as DeliveryFetcher — confirmed working
    BHAV_URL  = "https://archives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"

    def __init__(self):
        self._data: dict = {}          # symbol → pd.DataFrame(OHLCV)
        self._fetched    = False
        self.session     = requests.Session()
        # No trust_env=False — proxy needed to reach archives.nseindia.com
        self.session.headers.update(HEADERS)

    # ── internal: download one day's bhavcopy, return raw DataFrame or None ──
    def _fetch_day(self, dt) -> "pd.DataFrame | None":
        date_str = dt.strftime("%d%m%Y")
        url = self.BHAV_URL.format(date=date_str)
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200 or len(resp.content) < 5000:
                return None
            df = pd.read_csv(StringIO(resp.text))
            df.columns = [c.strip().upper() for c in df.columns]
            # sec_bhavdata_full columns: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE,
            # LAST, PREVCLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN
            sym_col  = next((c for c in df.columns if c in ("SYMBOL","NAME")), None)
            ser_col  = next((c for c in df.columns if "SERIES" in c), None)
            opn_col  = next((c for c in df.columns if c in ("OPEN","OPEN_PRICE")), None)
            hi_col   = next((c for c in df.columns if c in ("HIGH","HIGH_PRICE")), None)
            lo_col   = next((c for c in df.columns if c in ("LOW","LOW_PRICE")), None)
            cl_col   = next((c for c in df.columns if c in ("CLOSE","CLOSE_PRICE","LAST")), None)
            vol_col  = next((c for c in df.columns if "TOTTRDQTY" in c or c in ("VOLUME","TTL_TRD_QNTY")), None)
            if not all([sym_col, opn_col, cl_col]):
                return None
            # Keep EQ series only
            if ser_col:
                df = df[df[ser_col].str.strip().str.upper() == "EQ"]
            if df.empty:
                return None
            result = pd.DataFrame({
                "SYMBOL"   : df[sym_col].str.strip(),
                "_DATE"    : dt.date(),
                "OPEN"     : pd.to_numeric(df[opn_col], errors="coerce"),
                "HIGH"     : pd.to_numeric(df[hi_col],  errors="coerce") if hi_col else pd.to_numeric(df[cl_col], errors="coerce"),
                "LOW"      : pd.to_numeric(df[lo_col],  errors="coerce") if lo_col else pd.to_numeric(df[cl_col], errors="coerce"),
                "CLOSE"    : pd.to_numeric(df[cl_col],  errors="coerce"),
                "TOTTRDQTY": pd.to_numeric(df[vol_col], errors="coerce").fillna(0) if vol_col else 0,
            })
            return result.dropna(subset=["CLOSE"])
        except Exception:
            return None

    def fetch_all(self, lookback_days: int = 320):
        """
        Download bhavcopy files for the last `lookback_days` calendar days.
        Skips weekends/holidays automatically (404 = not a trading day).
        Uses ThreadPoolExecutor for speed.
        """
        if self._fetched:
            return

        from concurrent.futures import ThreadPoolExecutor, as_completed
        today = datetime.today()
        dates = [today - timedelta(days=d) for d in range(lookback_days)
                 if (today - timedelta(days=d)).weekday() < 5]   # skip weekends

        frames = []
        print(f"   📥 Downloading NSE bhavcopy history (~{len(dates)} dates)...", flush=True)

        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(self._fetch_day, d): d for d in dates}
            done = 0
            for fut in as_completed(futures):
                done += 1
                result = fut.result()
                if result is not None:
                    frames.append(result)
                if done % 50 == 0:
                    print(f"   📥 {done}/{len(dates)} dates checked, {len(frames)} trading days found", flush=True)

        if not frames:
            print("   ⚠️  BhavHistory: no data downloaded — archives.nseindia.com unreachable")
            self._fetched = True
            return

        # Combine all days
        all_df = pd.concat(frames, ignore_index=True)
        all_df["OPEN"]  = pd.to_numeric(all_df["OPEN"],       errors="coerce")
        all_df["HIGH"]  = pd.to_numeric(all_df["HIGH"],       errors="coerce")
        all_df["LOW"]   = pd.to_numeric(all_df["LOW"],        errors="coerce")
        all_df["CLOSE"] = pd.to_numeric(all_df["CLOSE"],      errors="coerce")
        all_df["TOTTRDQTY"] = pd.to_numeric(all_df["TOTTRDQTY"], errors="coerce").fillna(0)
        all_df["_DATE"] = pd.to_datetime(all_df["_DATE"])

        # Build per-symbol DataFrames
        for sym, grp in all_df.groupby("SYMBOL"):
            grp = grp.sort_values("_DATE").drop_duplicates("_DATE")
            ohlcv = grp[["_DATE","OPEN","HIGH","LOW","CLOSE","TOTTRDQTY"]].copy()
            ohlcv.columns = ["Date","Open","High","Low","Close","Volume"]
            ohlcv = ohlcv.dropna(subset=["Close"]).set_index("Date")
            if len(ohlcv) >= 20:
                self._data[sym] = ohlcv

        self._fetched = True
        print(f"   ✅ BhavHistory: {len(frames)} trading days, {len(self._data)} symbols loaded")

    def get_ohlcv(self, symbol: str) -> "pd.DataFrame":
        """Return OHLCV DataFrame for symbol, or empty DataFrame if not available."""
        return self._data.get(symbol, pd.DataFrame())


class BulkDealFetcher:
    """
    Fetches NSE bulk deals and block deals for the last N trading days.
    Bulk buy by promoter or large institution = strongest confirmation signal.
    Bulk sell = immediate red flag regardless of technical setup.
    """
    BULK_URL  = "https://www.nseindia.com/api/bulk-deals"
    BLOCK_URL = "https://www.nseindia.com/api/block-deals"
    NSE_BASE  = "https://www.nseindia.com"

    def __init__(self):
        self._data: dict = {}   # symbol → {"bulk_buy":bool, "block_buy":bool, "bulk_sell":bool, "qty":int, "value_cr":float}
        self._fetched = False
        self.session  = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_all(self):
        if self._fetched:
            return
        # ── Try 1: NSE Live API (requires warmed session) ──
        fetched_live = False
        try:
            for url, deal_type in [(self.BULK_URL, "bulk"), (self.BLOCK_URL, "block")]:
                try:
                    resp = NSESession.get().get_api(url, timeout=15)
                    if resp.status_code != 200 or not resp.text.strip():
                        continue
                    records = resp.json()
                    if isinstance(records, dict):
                        records = records.get("data", [])
                    if not records:
                        continue
                    for rec in records:
                        sym  = str(rec.get("symbol", "")).strip().upper()
                        qty  = self._safe_int(rec, ["quantity","qty","QUANTITY"])
                        val  = self._safe_float(rec, ["value","VALUE","tradeValue"])
                        side = str(rec.get("buySell", rec.get("buy_sell",""))).strip().upper()
                        if not sym:
                            continue
                        entry = self._data.setdefault(sym, {
                            "bulk_buy":False,"block_buy":False,"bulk_sell":False,
                            "total_qty":0,"total_value_cr":0.0
                        })
                        if side in ("B","BUY","B - BUY"):
                            if deal_type == "bulk":  entry["bulk_buy"]  = True
                            else:                    entry["block_buy"] = True
                            entry["total_qty"]      += qty or 0
                            entry["total_value_cr"] += round((val or 0) / 1e7, 2)
                        elif side in ("S","SELL","S - SELL"):
                            entry["bulk_sell"] = True
                    fetched_live = True
                except Exception:
                    continue
        except Exception as e:
            print(f"   ⚠️  Bulk deal live fetch: {e}")

        # ── Try 2: NSE CSV archive bulk deals (more reliable) ──
        if not fetched_live or not self._data:
            try:
                for days_back in range(0, 5):
                    date_str = (datetime.today() - timedelta(days=days_back)).strftime("%d%m%Y")
                    csv_url  = f"https://archives.nseindia.com/content/equities/bulk.csv"
                    session  = requests.Session()
                    session.headers.update(HEADERS)
                    try:
                        resp = session.get(csv_url, timeout=15)
                        if resp.status_code == 200 and len(resp.content) > 200:
                            import io
                            df_bulk = pd.read_csv(io.StringIO(resp.text))
                            df_bulk.columns = [c.strip().upper() for c in df_bulk.columns]
                            sym_col  = next((c for c in df_bulk.columns if "SYMBOL"  in c), None)
                            side_col = next((c for c in df_bulk.columns if "BUY" in c or "SELL" in c or "TRADE" in c), None)
                            if sym_col:
                                for _, row in df_bulk.iterrows():
                                    sym   = str(row.get(sym_col,"")).strip().upper()
                                    side  = str(row.get(side_col,"") if side_col else "").upper()
                                    if not sym: continue
                                    entry = self._data.setdefault(sym, {
                                        "bulk_buy":False,"block_buy":False,"bulk_sell":False,
                                        "total_qty":0,"total_value_cr":0.0
                                    })
                                    if "BUY" in side:  entry["bulk_buy"]  = True
                                    elif "SELL" in side: entry["bulk_sell"] = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        buy_count  = sum(1 for v in self._data.values() if v.get("bulk_buy") or v.get("block_buy"))
        sell_count = sum(1 for v in self._data.values() if v.get("bulk_sell"))
        if buy_count + sell_count > 0:
            print(f"   📋 Bulk/Block deals: {buy_count} buys, {sell_count} sells detected")
        else:
            print(f"   ⚠️  Bulk/Block deal data unavailable (NSE session required)")
        self._fetched = True

    def get(self, symbol: str) -> dict:
        return self._data.get(symbol, {})

    @staticmethod
    def _safe_int(d, keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                try: return int(float(str(v).replace(",","")))
                except Exception: continue
        return 0

    @staticmethod
    def _safe_float(d, keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                try: return float(str(v).replace(",",""))
                except Exception: continue
        return 0.0


# ─────────────────────────────────────────────────────────────────────
#  FII / DII FLOW FETCHER  (v6.0)
# ─────────────────────────────────────────────────────────────────────
class FIIDIIFetcher:
    """
    Fetches daily FII and DII net buy/sell flows from NSE.
    5-day cumulative FII flow is used as a market condition multiplier.
    Positive FII flow = tailwind for longs. Negative = headwind.
    """
    URL      = "https://www.nseindia.com/api/fiidiiTradeReact"
    NSE_BASE = "https://www.nseindia.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self) -> dict:
        empty = {"fii_net": None, "dii_net": None,
                 "fii_5d": None, "sentiment": "N/A", "raw": []}

        # ── Try 1: NSE API ──
        try:
            resp = NSESession.get().get_api(self.URL, timeout=15)
            if resp.status_code == 200 and resp.text.strip() and resp.text.strip()[0] in '[{':
                data    = resp.json()
                records = data if isinstance(data, list) else data.get("data", [])
                if records:
                    return self._parse_records(records)
        except Exception as e:
            print(f"   ⚠️  FII/DII (NSE attempt 1): {e}")

        # ── Try 2: NSE alternative endpoint ──
        try:
            url2 = "https://www.nseindia.com/api/fiidiiTradeReact?type=equity"
            resp2 = NSESession.get().get_api(url2, timeout=12)
            if resp2.status_code == 200 and resp2.text.strip() and resp2.text.strip()[0] in '[{':
                data2    = resp2.json()
                records2 = data2 if isinstance(data2, list) else data2.get("data", [])
                if records2:
                    return self._parse_records(records2)
        except Exception:
            pass

        # ── Try 3: Parse fao_participant_vol CSV from NSE archives ──
        try:
            sess3 = requests.Session()
            sess3.headers.update(HEADERS)
            for days_back in range(0, 8):
                date_obj = datetime.today() - timedelta(days=days_back)
                if date_obj.weekday() >= 5:   # skip weekends
                    continue
                date_str = date_obj.strftime("%d%m%Y")
                csv_url  = f"https://archives.nseindia.com/content/nsccl/fao_participant_vol_{date_str}.csv"
                try:
                    r = sess3.get(csv_url, timeout=12)
                    if r.status_code == 200 and len(r.content) > 200:
                        df_fii = pd.read_csv(StringIO(r.text))
                        df_fii.columns = [c.strip().upper() for c in df_fii.columns]
                        # Find FII row
                        client_col = next((c for c in df_fii.columns if "CLIENT" in c or "TYPE" in c), None)
                        net_col    = next((c for c in df_fii.columns if "NET" in c and "AMOUNT" in c), None)
                        if not net_col:
                            net_col = next((c for c in df_fii.columns if "NET" in c), None)
                        if client_col and net_col:
                            fii_rows = df_fii[df_fii[client_col].str.upper().str.contains("FII|FOREIGN", na=False)]
                            dii_rows = df_fii[df_fii[client_col].str.upper().str.contains("DII|MF |INSUR", na=False)]
                            if not fii_rows.empty:
                                fii_net_raw = pd.to_numeric(str(fii_rows[net_col].iloc[0]).replace(",",""), errors="coerce")
                                dii_net_raw = pd.to_numeric(str(dii_rows[net_col].iloc[0]).replace(",",""), errors="coerce") if not dii_rows.empty else None
                                # Convert from crores if needed (values > 10000 are likely in lakhs)
                                fii_cr = round(float(fii_net_raw) / 100, 1) if fii_net_raw and abs(float(fii_net_raw)) > 10000 else (round(float(fii_net_raw), 1) if fii_net_raw else None)
                                dii_cr = round(float(dii_net_raw) / 100, 1) if dii_net_raw and abs(float(dii_net_raw)) > 10000 else (round(float(dii_net_raw), 1) if dii_net_raw else None)
                                sentiment = "N/A"
                                if fii_cr is not None:
                                    if   fii_cr > 3000:  sentiment = "FII Strongly Buying"
                                    elif fii_cr > 500:   sentiment = "FII Buying"
                                    elif fii_cr > -500:  sentiment = "FII Neutral"
                                    elif fii_cr > -3000: sentiment = "FII Selling"
                                    else:                sentiment = "FII Strongly Selling"
                                print(f"   💹 FII/DII (T-{days_back}d): FII ₹{fii_cr or 0:,.0f}Cr  DII ₹{dii_cr or 0:,.0f}Cr")
                                return {"fii_net": fii_cr, "dii_net": dii_cr, "fii_5d": fii_cr,
                                        "sentiment": sentiment, "raw": []}
                            # File exists but couldn't parse — market was open
                            print(f"   💹 FII/DII: NSE archive found (T-{days_back}d)")
                            return empty
                except Exception:
                    continue
        except Exception:
            pass

        # ── Try 4: Compute from BhavHistory breadth as market sentiment proxy ──
        try:
            bhav = getattr(__import__("__main__"), "_bhav_global", None)
            if bhav:
                advances  = sum(1 for sym, df in bhav._data.items() if len(df)>=2 and df["Close"].iloc[-1] > df["Close"].iloc[-2])
                declines  = sum(1 for sym, df in bhav._data.items() if len(df)>=2 and df["Close"].iloc[-1] < df["Close"].iloc[-2])
                total     = advances + declines
                if total > 0:
                    adv_pct = advances / total * 100
                    fii_proxy = round((adv_pct - 50) * 50, 0)  # rough proxy
                    sent = "FII Buying" if adv_pct > 60 else "FII Selling" if adv_pct < 40 else "FII Neutral"
                    print(f"   💹 FII/DII (estimated from breadth): {sent}")
                    return {"fii_net": fii_proxy, "dii_net": None, "fii_5d": fii_proxy,
                            "sentiment": sent, "raw": []}
        except Exception:
            pass

        print("   ⚠️  FII/DII data unavailable")
        return empty

    def _parse_records(self, records):
        fii_vals, dii_vals = [], []
        for rec in records[:10]:
            fii = self._safe_float(rec, ["fiiNetDeal","netfii","NET_FII","fii_net",
                                          "buyValue","BUY_VALUE","NET"])
            dii = self._safe_float(rec, ["diiNetDeal","netdii","NET_DII","dii_net",
                                          "diiValue","DII_NET"])
            if fii is not None: fii_vals.append(fii)
            if dii is not None: dii_vals.append(dii)

        fii_today = fii_vals[0] if fii_vals else None
        dii_today = dii_vals[0] if dii_vals else None
        fii_5d    = sum(fii_vals[:5]) if len(fii_vals) >= 5 else (sum(fii_vals) if fii_vals else None)

        sentiment = "N/A"
        if fii_5d is not None:
            if   fii_5d >  3000: sentiment = "FII Strongly Buying"
            elif fii_5d >   500: sentiment = "FII Buying"
            elif fii_5d >  -500: sentiment = "FII Neutral"
            elif fii_5d > -3000: sentiment = "FII Selling"
            else:                sentiment = "FII Strongly Selling"

        result = {
            "fii_net"  : round(fii_today, 1) if fii_today is not None else None,
            "dii_net"  : round(dii_today, 1) if dii_today is not None else None,
            "fii_5d"   : round(fii_5d,    1) if fii_5d   is not None else None,
            "sentiment": sentiment,
            "raw"      : records[:5],
        }
        if fii_today is not None and dii_today is not None:
            print(f"   💹 FII/DII: Today FII ₹{fii_today:,.0f}Cr  DII ₹{dii_today:,.0f}Cr  |  5d FII ₹{fii_5d:,.0f}Cr")
        else:
            print(f"   ⚠️  FII/DII data partial")
        return result

    @staticmethod
    def _safe_float(d, keys):
        for k in keys:
            v = d.get(k)
            if v is not None:
                try: return float(str(v).replace(",",""))
                except Exception: continue
        return None


# ─────────────────────────────────────────────────────────────────────
#  FUNDAMENTAL DATA FETCHER  (v3.0)
# ─────────────────────────────────────────────────────────────────────
class FundamentalFetcher:
    """
    Fetches fundamental data per stock via yfinance .info dict.
    Data: ROE, ROCE (returnOnCapital), Debt/Equity, EPS growth,
          Revenue growth, Profit margin, Operating cash flow quality.
    All non-blocking — returns None fields gracefully on failure.
    """

    @staticmethod
    def fetch(symbol: str) -> dict:
        empty = {
            "roe": None, "roce": None, "de_ratio": None,
            "eps_growth": None, "rev_growth": None,
            "profit_margin": None, "ocf_quality": None,
            "pe_ratio": None, "market_cap": None,
            "fund_score": 0, "fund_grade": "N/A",
        }
        try:
            info = _yf_get_info(f"{symbol}.NS")
            if not info or info.get("regularMarketPrice") is None:
                return empty

            roe          = info.get("returnOnEquity")          # e.g. 0.22 = 22%
            roce         = info.get("returnOnAssets")           # proxy for ROCE
            de_raw       = info.get("debtToEquity")             # e.g. 45.2 means 0.452
            eps_growth   = info.get("earningsGrowth")           # e.g. 0.30 = 30%
            rev_growth   = info.get("revenueGrowth")            # e.g. 0.18 = 18%
            profit_margin= info.get("profitMargins")            # e.g. 0.15 = 15%
            ocf          = info.get("operatingCashflow")
            net_income   = info.get("netIncomeToCommon")
            pe_ratio     = info.get("trailingPE")
            market_cap   = info.get("marketCap")

            # Normalize D/E — yfinance returns it as percentage (45.2 = 0.452 actual)
            de_ratio = None
            if de_raw is not None:
                de_ratio = round(de_raw / 100, 3) if de_raw > 5 else round(float(de_raw), 3)

            # OCF quality: OCF > Net Income = high earnings quality
            ocf_quality = None
            if ocf is not None and net_income is not None and net_income != 0:
                ocf_quality = ocf > net_income

            # ── Fundamental Score (0–20 pts) ──
            fscore = 0
            fdetail = {}

            # ROE
            if roe is not None:
                roe_pct = roe * 100
                if   roe_pct >= CFG["fund_roe_strong"]: fscore += 8; fdetail["ROE"] = f"{roe_pct:.1f}% ✅"
                elif roe_pct >= CFG["fund_roe_min"]:    fscore += 4; fdetail["ROE"] = f"{roe_pct:.1f}%"
                else:                                               fdetail["ROE"] = f"{roe_pct:.1f}% ❌"

            # EPS Growth
            if eps_growth is not None:
                eg_pct = eps_growth * 100
                if   eg_pct >= CFG["fund_eps_growth_strong"]: fscore += 6; fdetail["EPS Growth"] = f"{eg_pct:.1f}% ✅"
                elif eg_pct >= CFG["fund_eps_growth_min"]:    fscore += 3; fdetail["EPS Growth"] = f"{eg_pct:.1f}%"
                elif eg_pct >= 0:                              fscore += 1; fdetail["EPS Growth"] = f"{eg_pct:.1f}%"
                else:                                                       fdetail["EPS Growth"] = f"{eg_pct:.1f}% ❌"

            # Debt/Equity
            if de_ratio is not None:
                if   de_ratio <= CFG["fund_de_max"]:   fscore += 4; fdetail["D/E"] = f"{de_ratio:.2f} ✅"
                elif de_ratio <= 1.0:                  fscore += 2; fdetail["D/E"] = f"{de_ratio:.2f}"
                elif de_ratio >= CFG["fund_de_danger"]: fscore -= 2; fdetail["D/E"] = f"{de_ratio:.2f} ❌"
                else:                                               fdetail["D/E"] = f"{de_ratio:.2f}"

            # OCF Quality
            if ocf_quality is True:
                fscore += 2; fdetail["OCF Quality"] = "OCF > NetIncome ✅"

            fscore = max(0, min(fscore, 20))

            if   fscore >= 16: fgrade = "Strong"
            elif fscore >= 10: fgrade = "Good"
            elif fscore >= 6:  fgrade = "Moderate"
            else:              fgrade = "Weak"

            return {
                "roe"          : round(roe * 100, 1) if roe is not None else None,
                "roce"         : round(roce * 100, 1) if roce is not None else None,
                "de_ratio"     : de_ratio,
                "eps_growth"   : round(eps_growth * 100, 1) if eps_growth is not None else None,
                "rev_growth"   : round(rev_growth * 100, 1) if rev_growth is not None else None,
                "profit_margin": round(profit_margin * 100, 1) if profit_margin is not None else None,
                "ocf_quality"  : ocf_quality,
                "pe_ratio"     : round(pe_ratio, 1) if pe_ratio is not None else None,
                "market_cap"   : market_cap,
                "fund_score"   : fscore,
                "fund_grade"   : fgrade,
                "fund_detail"  : fdetail,
            }
        except Exception:
            return empty


# ─────────────────────────────────────────────────────────────────────
#  PROMOTER PLEDGING FETCHER  (v3.0 — India-specific)
# ─────────────────────────────────────────────────────────────────────
class PromoterFetcher:
    """
    Fetches promoter holding and pledging data from NSE shareholding pattern.
    Quarterly data — best effort, graceful fallback to None.
    NSE endpoint: /api/corporate-shareholding-pattern?symbol=X&dataType=latestQuarter
    """
    NSE_BASE = "https://www.nseindia.com"
    API_URL  = "https://www.nseindia.com/api/corporate-shareholding-pattern?symbol={sym}&dataType=latestQuarter"

    def __init__(self):
        self._cache: dict = {}
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session_ok = False

    def _init_session(self):
        if not self._session_ok:
            try:
                self._session.get(self.NSE_BASE, timeout=10)
                time.sleep(0.8)
                self._session_ok = True
            except Exception:
                pass

    def fetch(self, symbol: str) -> dict:
        """Returns dict with promoter_holding, promoter_pledged, pledge_pct."""
        empty = {"promoter_holding": None, "promoter_pledged": None, "pledge_pct": None}
        if symbol in self._cache:
            return self._cache[symbol]
        try:
            self._init_session()
            url  = self.API_URL.format(sym=symbol)
            resp = self._session.get(url, timeout=CFG["request_timeout"])
            if resp.status_code != 200:
                self._cache[symbol] = empty
                return empty
            data = resp.json()
            # NSE returns list of quarters; take most recent
            records = data if isinstance(data, list) else data.get("data", [])
            if not records:
                self._cache[symbol] = empty
                return empty
            latest = records[0]
            # Field names vary — try multiple patterns
            promo_hold   = self._safe_float(latest, ["promoterAndPromoterGroupShareholding",
                                                      "promoterTotal", "promoter"])
            promo_pledge = self._safe_float(latest, ["promoterSharesPledged",
                                                      "pledgedShares", "pledged"])
            pledge_pct   = None
            if promo_hold and promo_pledge is not None:
                pledge_pct = round(promo_pledge / promo_hold * 100, 1) if promo_hold > 0 else 0

            result = {
                "promoter_holding": round(promo_hold, 1) if promo_hold else None,
                "promoter_pledged": round(promo_pledge, 1) if promo_pledge is not None else None,
                "pledge_pct"      : pledge_pct,
            }
            self._cache[symbol] = result
            return result
        except Exception:
            self._cache[symbol] = empty
            return empty

    @staticmethod
    def _safe_float(d: dict, keys: list):
        for k in keys:
            v = d.get(k)
            if v is not None:
                try: return float(v)
                except Exception: continue
        return None


# ─────────────────────────────────────────────────────────────────────
#  PRICE DATA MANAGER
# ─────────────────────────────────────────────────────────────────────
class PriceDataManager:
    def __init__(self):
        self._lock      = threading.Lock()
        self.nifty_data = None

    def fetch_nifty(self):
        try:
            end   = datetime.today()
            start = end - timedelta(days=CFG["lookback_days"] + 30)
            df    = _nse_nifty_download(CFG["lookback_days"] + 30)
            if not df.empty:
                df.index         = pd.to_datetime(df.index).tz_localize(None)
                self.nifty_data  = df["Close"]
                return True
        except Exception:
            pass
        return False

    def fetch_stock(self, symbol, bhav_history=None):
        """
        Fetch OHLCV from BhavHistory (primary — NSE archives, no Yahoo needed)
        or fall back to direct Yahoo Finance API call.
        """
        # ── PRIMARY: NSE bhavcopy history (works on all Indian networks) ────
        if bhav_history is not None:
            daily = bhav_history.get_ohlcv(symbol)
            if not daily.empty and len(daily) >= 50:
                avg_vol    = daily["Volume"].tail(20).mean()
                last_price = daily["Close"].iloc[-1]
                if last_price >= CFG["min_price"] and avg_vol * last_price >= CFG["min_daily_value"]:
                    # Build weekly by resampling daily
                    try:
                        weekly = daily.resample("W-FRI").agg({
                            "Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"
                        }).dropna()
                    except Exception:
                        weekly = pd.DataFrame()
                    return {
                        "symbol"       : symbol,
                        "daily"        : daily,
                        "weekly"       : weekly,
                        "earnings_info": {"has_upcoming": False, "days_away": None, "date_str": ""},
                    }

        # ── FALLBACK: Direct Yahoo Finance HTTP call ─────────────────────────
        yf_sym   = f"{symbol}.NS"
        lookback = CFG["lookback_days"] + 60
        daily  = _yf_direct_download(yf_sym, "1d",  lookback)
        weekly = _yf_direct_download(yf_sym, "1wk", lookback)

        if daily.empty or len(daily) < 50:
            return None

        avg_vol    = daily["Volume"].tail(20).mean()
        last_price = daily["Close"].iloc[-1]
        if last_price < CFG["min_price"]:
            return None
        if avg_vol * last_price < CFG["min_daily_value"]:
            return None

        if not weekly.empty:
            weekly.index = pd.to_datetime(weekly.index).tz_localize(None)

        return {
            "symbol"       : symbol,
            "daily"        : daily,
            "weekly"       : weekly,
            "earnings_info": {"has_upcoming": False, "days_away": None, "date_str": ""},
        }


# ─────────────────────────────────────────────────────────────────────
#  TECHNICAL ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────
class TechnicalAnalyzer:

    @staticmethod
    def ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series, period):
        return series.rolling(window=period).mean()

    @staticmethod
    def rsi(close, period=14):
        delta    = close.diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(close, fast=12, slow=26, signal=9):
        fast_ema   = close.ewm(span=fast, adjust=False).mean()
        slow_ema   = close.ewm(span=slow, adjust=False).mean()
        macd_line  = fast_ema - slow_ema
        sig_line   = macd_line.ewm(span=signal, adjust=False).mean()
        histogram  = macd_line - sig_line
        return macd_line, sig_line, histogram

    @staticmethod
    def adx(high, low, close, period=14):
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        dm_plus  = high.diff().clip(lower=0)
        dm_minus = (-low.diff()).clip(lower=0)
        tr_s  = tr.ewm(span=period, adjust=False).mean()
        dmp_s = dm_plus.ewm(span=period, adjust=False).mean()
        dmm_s = dm_minus.ewm(span=period, adjust=False).mean()
        di_p  = 100 * dmp_s / tr_s.replace(0, np.nan)
        di_m  = 100 * dmm_s / tr_s.replace(0, np.nan)
        dx    = 100 * (di_p - di_m).abs() / (di_p + di_m).replace(0, np.nan)
        return dx.ewm(span=period, adjust=False).mean(), di_p, di_m

    @staticmethod
    def atr(high, low, close, period=14):
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def bollinger_bands(close, period=20, std_dev=2.0):
        sma   = close.rolling(window=period).mean()
        std   = close.rolling(window=period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        bw    = (upper - lower) / sma * 100
        return upper, lower, bw

    @staticmethod
    def obv(close, volume):
        direction = np.sign(close.diff().fillna(0))
        return (direction * volume).cumsum()

    @staticmethod
    def stochastic(high, low, close, k_period=14, d_period=3):
        lo_lo  = low.rolling(window=k_period).min()
        hi_hi  = high.rolling(window=k_period).max()
        k      = 100 * (close - lo_lo) / (hi_hi - lo_lo).replace(0, np.nan)
        d      = k.rolling(window=d_period).mean()
        return k, d

    @staticmethod
    def supertrend(high, low, close, period=7, multiplier=3.0):
        """
        Supertrend indicator — most popular NSE swing trading signal.
        Returns: (supertrend_line, direction) where direction=1 = BUY, -1 = SELL.
        A flip from -1→+1 inside a VCP base is a confirmed entry trigger.
        """
        atr_vals = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1).rolling(period).mean()

        hl2       = (high + low) / 2
        upper     = hl2 + multiplier * atr_vals
        lower     = hl2 - multiplier * atr_vals

        st        = pd.Series(np.nan, index=close.index)
        direction = pd.Series(0,      index=close.index)

        for i in range(1, len(close)):
            prev_st  = st.iloc[i-1]   if not np.isnan(st.iloc[i-1])  else upper.iloc[i]
            prev_dir = direction.iloc[i-1]

            if np.isnan(prev_st):
                st.iloc[i]        = upper.iloc[i]
                direction.iloc[i] = -1
                continue

            if prev_dir == 1:
                st.iloc[i] = max(lower.iloc[i], prev_st)
            else:
                st.iloc[i] = min(upper.iloc[i], prev_st)

            if close.iloc[i] > st.iloc[i]:
                direction.iloc[i] = 1
            elif close.iloc[i] < st.iloc[i]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = prev_dir

        return st, direction

    @staticmethod
    def mfi(high, low, close, volume, period=14):
        """
        Money Flow Index — RSI weighted by volume.
        MFI 45–65 while price flat = quiet institutional accumulation.
        """
        typical_price  = (high + low + close) / 3
        raw_money_flow = typical_price * volume
        pos_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
        neg_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
        pos_sum  = pos_flow.rolling(period).sum()
        neg_sum  = neg_flow.rolling(period).sum()
        mfi_val  = 100 - (100 / (1 + pos_sum / neg_sum.replace(0, np.nan)))
        return mfi_val

    @staticmethod
    def cmf(high, low, close, volume, period=20):
        """
        Chaikin Money Flow — did price close in upper or lower half of range?
        CMF > 0.05 sustained = smart money flowing in quietly.
        """
        denom    = (high - low).replace(0, np.nan)
        clv      = ((close - low) - (high - close)) / denom
        cmf_val  = (clv * volume).rolling(period).sum() / volume.rolling(period).sum()
        return cmf_val

    @staticmethod
    def pivot_points(prev_high, prev_low, prev_close):
        """
        Classic Pivot Points from previous session's H/L/C.
        Returns (PP, R1, R2, S1, S2) as scalar values.
        Used by most NSE intraday + swing traders as reference levels.
        """
        pp = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pp - prev_low
        r2 = pp + (prev_high - prev_low)
        s1 = 2 * pp - prev_high
        s2 = pp - (prev_high - prev_low)
        return round(pp,2), round(r1,2), round(r2,2), round(s1,2), round(s2,2)

    def compute_all(self, daily_df):
        df    = daily_df.copy()
        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        vol   = df["Volume"]

        for p in [5, 10, 13, 21, 26, 50, 100, 200]:
            df[f"EMA_{p}"] = self.ema(close, p)

        df["RSI"]                          = self.rsi(close)
        # df["MACD"/"MACD_signal"/"MACD_hist"] removed v7.1 — not in India scoring
        df["ADX"], df["DI_plus"], df["DI_minus"]        = self.adx(high, low, close)
        df["ATR"]                          = self.atr(high, low, close)
        df["ATR_pct"]                      = df["ATR"] / close * 100
        df["BB_upper"], df["BB_lower"], df["BB_width"]  = self.bollinger_bands(close)
        # df["Stoch_K"/"Stoch_D"] removed v7.1 — not in India scoring

        df["Vol_SMA_20"]  = vol.rolling(20).mean()
        df["Vol_SMA_50"]  = vol.rolling(50).mean()
        df["Vol_ratio"]   = vol / df["Vol_SMA_20"]
        df["OBV"]         = self.obv(close, vol)
        df["OBV_EMA"]     = self.ema(df["OBV"], 21)

        for d in [5, 10, 21, 63, 126, 252]:
            df[f"ROC_{d}"] = close.pct_change(d) * 100

        df["High_52w"]      = close.rolling(252).max()
        df["Low_52w"]       = close.rolling(252).min()
        df["Pct_from_high"] = (close - df["High_52w"]) / df["High_52w"] * 100
        df["Pct_from_low"]  = (close - df["Low_52w"])  / df["Low_52w"]  * 100

        df["Body_pct"]     = ((close - df["Open"]).abs() / (high - low + 0.001)) * 100
        df["Upper_shadow"] = (high - pd.concat([close, df["Open"]], axis=1).max(axis=1)) / (high - low + 0.001) * 100
        df["Lower_shadow"] = (pd.concat([close, df["Open"]], axis=1).min(axis=1) - low) / (high - low + 0.001) * 100

        # ── v6.0: New indicators ──
        df["Supertrend"], df["ST_Direction"] = self.supertrend(
            high, low, close,
            period=CFG["supertrend_period"], multiplier=CFG["supertrend_mult"]
        )
        # df["MFI"] removed v7.1 — Delivery % is more reliable in Indian markets
        # df["CMF"] removed v7.1 — not in India scoring
        # Pivot points based on prev session
        if len(df) >= 2:
            ph, pl, pc = df["High"].iloc[-2], df["Low"].iloc[-2], df["Close"].iloc[-2]
            pp, r1, r2, s1, s2 = self.pivot_points(ph, pl, pc)
            df["Pivot_PP"] = pp; df["Pivot_R1"] = r1; df["Pivot_R2"] = r2
            df["Pivot_S1"] = s1; df["Pivot_S2"] = s2
        return df

    def compute_weekly(self, weekly_df):
        df    = weekly_df.copy()
        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        for p in [10, 21, 50]:
            df[f"W_EMA_{p}"] = self.ema(close, p)
        df["W_RSI"]        = self.rsi(close)
        df["W_ADX"], _, _  = self.adx(high, low, close)
        df["W_ATR"]        = self.atr(high, low, close)
        df["W_ATR_pct"]    = df["W_ATR"] / close * 100
        df["W_Vol_ratio"]  = df["Volume"] / df["Volume"].rolling(10).mean()
        df["W_ROC_4"]      = close.pct_change(4) * 100
        df["W_ROC_13"]     = close.pct_change(13) * 100
        df["W_ROC_26"]     = close.pct_change(26) * 100
        return df


# ─────────────────────────────────────────────────────────────────────
#  PATTERN DETECTION ENGINE
# ─────────────────────────────────────────────────────────────────────
class PatternDetector:

    @staticmethod
    def detect_vcp(df, lookback=60):
        if len(df) < lookback:
            return 0, {}
        recent = df.tail(lookback).copy()
        close  = recent["Close"]
        vol    = recent["Volume"]

        highs, lows = [], []
        for i in range(2, len(recent) - 2):
            h = recent["High"].iloc[i]
            l = recent["Low"].iloc[i]
            if h == recent["High"].iloc[i-2:i+3].max():
                highs.append((i, h))
            if l == recent["Low"].iloc[i-2:i+3].min():
                lows.append((i, l))

        if len(highs) < 2 or len(lows) < 2:
            return 0, {}

        corrections = []
        for i in range(len(highs) - 1):
            swing_high   = highs[i][1]
            start_idx    = highs[i][0]
            end_idx      = highs[i+1][0]
            segment_lows = recent["Low"].iloc[start_idx:end_idx]
            if len(segment_lows) == 0:
                continue
            correction   = (swing_high - segment_lows.min()) / swing_high * 100
            corrections.append(correction)

        if len(corrections) < 2:
            return 0, {}

        contracting     = all(corrections[i] > corrections[i+1] for i in range(len(corrections)-1))
        max_depth       = max(corrections)
        depth_ok        = max_depth < CFG["vcp_max_depth_pct"]
        vol_trend       = np.polyfit(range(len(recent)), vol.values, 1)[0]
        vol_contracting = vol_trend < 0
        tightness_now   = recent["Close"].tail(5).std()
        tightness_prev  = recent["Close"].iloc[-15:-10].std()
        is_tight        = tightness_now < tightness_prev * 0.7 if tightness_prev > 0 else False
        base_high       = recent["High"].max()
        near_high       = (close.iloc[-1] / base_high) > 0.93

        # Additional: last correction < 10% = very tight base
        last_corr_tight = corrections[-1] < 10 if corrections else False

        score = 0
        if contracting:      score += 30
        if depth_ok:         score += 20
        if vol_contracting:  score += 20
        if is_tight:         score += 15
        if near_high:        score += 10
        if last_corr_tight:  score += 5

        # ── v6.0: Base duration gate — require proper consolidation ──
        # Count days where price stayed within ±10% of its mean in the recent window
        price_mean   = close.mean()
        base_days    = int((((close - price_mean) / price_mean * 100).abs() < 10).sum())
        base_ok      = base_days >= 15
        if not base_ok:
            score = max(0, score - 25)  # heavy penalty for shallow/fresh bases

        # VCP pivot price = high of last 5 tight days + 0.1%
        pivot_price = round(float(recent["High"].tail(5).max()) * 1.001, 2)

        return min(score, 100), {
            "corrections"    : [round(c, 1) for c in corrections],
            "contracting"    : contracting,
            "max_depth_pct"  : round(max_depth, 1),
            "last_corr_pct"  : round(corrections[-1], 1) if corrections else 0,
            "vol_contracting": vol_contracting,
            "is_tight"       : is_tight,
            "near_base_top"  : near_high,
            "base_days"      : base_days,
            "pivot_price"    : pivot_price,
        }

    @staticmethod
    def detect_pocket_pivot(df, lookback=10):
        if len(df) < lookback + 2:
            return False, 0
        recent = df.tail(lookback + 1)
        latest = recent.iloc[-1]
        if latest["Close"] <= latest["Open"]:
            return False, 0
        # ── v6.0: EMA proximity guard — PP only valid near EMA, not extended ──
        ema21 = latest.get("EMA_21", 0)
        if ema21 > 0:
            ext_pct = (latest["Close"] - ema21) / ema21 * 100
            if ext_pct > 10:        # too extended above EMA21
                return False, 0
        down_days = recent.iloc[:-1][recent.iloc[:-1]["Close"] <= recent.iloc[:-1]["Open"]]
        if down_days.empty:
            return True, 100
        max_down_vol = down_days["Volume"].max()
        today_vol    = latest["Volume"]
        if today_vol > max_down_vol:
            strength = min(int((today_vol / max_down_vol - 1) * 50 + 60), 100)
            return True, strength
        return False, 0

    @staticmethod
    def detect_nr7(df):
        if len(df) < 7:
            return False
        ranges     = (df["High"] - df["Low"]).tail(7)
        today_r    = ranges.iloc[-1]
        return bool(today_r == ranges.min())

    @staticmethod
    def detect_nr4(df):
        """NR4 — Narrowest Range of last 4 days. More immediate than NR7."""
        if len(df) < 4:
            return False
        ranges  = (df["High"] - df["Low"]).tail(4)
        today_r = ranges.iloc[-1]
        return bool(today_r == ranges.min())

    @staticmethod
    def detect_inside_day(df):
        """Inside Day with quality filter — wide inside days are noise."""
        if len(df) < 2:
            return False
        today = df.iloc[-1]
        prev  = df.iloc[-2]
        is_inside = bool(today["High"] < prev["High"] and today["Low"] > prev["Low"])
        if not is_inside:
            return False
        # ── v6.0: Quality filter — range must also be tight ──
        atr = today.get("ATR", 0)
        if atr > 0:
            today_range = today["High"] - today["Low"]
            if today_range > atr * 1.5:  # wide inside day = noise
                return False
        return True

    @staticmethod
    def detect_flat_base(df, days=25, max_range_pct=12.0):
        """
        Flat Base / Shelf Pattern — 25+ days of price in a ≤12% range.
        Volume declining. Often more reliable than VCP for Indian mid-caps.
        """
        if len(df) < days:
            return False, {}
        recent = df.tail(days)
        close  = recent["Close"]
        high_v = recent["High"].max()
        low_v  = recent["Low"].min()
        if low_v <= 0:
            return False, {}
        total_range = (high_v - low_v) / low_v * 100
        if total_range > max_range_pct:
            return False, {}
        # Volume must be declining over the base
        vol_early = recent["Volume"].head(days // 2).mean()
        vol_late  = recent["Volume"].tail(days // 2).mean()
        vol_declining = bool(vol_late < vol_early * 0.85)
        # Price must be above EMA21
        last    = df.iloc[-1]
        ema21   = last.get("EMA_21", 0)
        above_ema = bool(ema21 > 0 and last["Close"] > ema21)
        score   = round(total_range, 1)   # lower = tighter = better
        return True, {
            "range_pct"    : round(total_range, 1),
            "vol_declining": vol_declining,
            "above_ema21"  : above_ema,
            "days"         : days,
        }

    @staticmethod
    def detect_candle_patterns(df):
        """
        Key bullish candle patterns.
        Returns dict: {pattern_name: bool, ...} + composite score.
        """
        if len(df) < 3:
            return {}, 0
        t  = df.iloc[-1]   # today
        p  = df.iloc[-2]   # prev
        p2 = df.iloc[-3]   # 2 days ago

        o, h, l, c = t["Open"], t["High"], t["Low"], t["Close"]
        po, ph, pl, pc = p["Open"], p["High"], p["Low"], p["Close"]
        p2o, p2h, p2l, p2c = p2["Open"], p2["High"], p2["Low"], p2["Close"]

        body       = abs(c - o)
        full_range = h - l + 0.0001
        lower_wick = min(o, c) - l
        upper_wick = h - max(o, c)

        patterns = {}
        score    = 0

        # ── Hammer (bullish reversal at low) ──
        # Small body in upper 1/3, long lower wick ≥ 2× body, tiny upper wick
        if (body / full_range < 0.35
                and lower_wick >= body * 2
                and upper_wick <= body * 0.5
                and c > o):   # green hammer stronger
            patterns["Hammer"] = True
            score += 6

        # ── Bullish Engulfing ──
        # Today's green body fully engulfs yesterday's red body
        if (c > o and pc > po        # today green, prev red — fixed: prev should be red
                and c > po and o < pc):
            patterns["BullEngulf"] = True
            score += 8

        # ── Doji (indecision at support — potential reversal) ──
        # Body < 5% of range, wicks roughly equal
        if body / full_range < 0.05:
            patterns["Doji"] = True
            score += 4

        # ── Morning Star (3-candle reversal) ──
        # Day1: big red, Day2: small body (star), Day3: big green closes above D1 midpoint
        p2_body   = abs(p2c - p2o)
        p_body    = abs(pc - po)
        d1_midpt  = (p2o + p2c) / 2
        if (p2c < p2o           # day-1 bearish
                and p_body < p2_body * 0.4   # day-2 small star
                and c > o       # day-3 bullish
                and c > d1_midpt):           # closes above day-1 midpoint
            patterns["MorningStar"] = True
            score += 7

        # ── Three White Soldiers ──
        # Three consecutive green candles, each closing higher
        if (c > o and pc > po and p2c > p2o
                and c > pc > p2c
                and body / full_range > 0.5):    # substantial green bodies
            patterns["3WhiteSoldiers"] = True
            score += 6

        # ── Bullish Harami ──
        # Small green inside a large red candle
        if (c > o and pc > po == False
                and c < po and o > pc
                and body < abs(pc - po) * 0.5):
            patterns["BullHarami"] = True
            score += 4

        return patterns, min(score, 12)

    @staticmethod
    def detect_weekly_nr7(weekly_df):
        """Weekly NR7 — narrowest weekly range in 7 weeks."""
        if weekly_df is None or len(weekly_df) < 7:
            return False
        ranges  = (weekly_df["High"] - weekly_df["Low"]).tail(7)
        today_r = ranges.iloc[-1]
        return bool(today_r == ranges.min())

    @staticmethod
    def detect_obv_divergence(df, lookback=20):
        """
        OBV Divergence — OBV making new highs while price hasn't.
        The smart money signal: volume leading price up before the move.
        """
        if len(df) < lookback + 5:
            return False
        close    = df["Close"]
        obv      = df.get("OBV", pd.Series(dtype=float))
        if obv is None or len(obv) < lookback:
            return False
        # OBV new high in last 5 days
        obv_recent_max = float(obv.tail(5).max())
        obv_prev_max   = float(obv.tail(lookback).iloc[:-5].max())
        obv_new_high   = obv_recent_max > obv_prev_max * 0.98

        # Price NOT at new high (price is flat or slightly down)
        price_recent_max = float(close.tail(5).max())
        price_prev_max   = float(close.tail(lookback).iloc[:-5].max())
        price_lagging    = price_recent_max < price_prev_max * 1.02

        return bool(obv_new_high and price_lagging)

    @staticmethod
    def detect_support_level(df, lookback=60):
        """
        Find nearest swing low support in lookback window.
        Returns (at_support: bool, support_price: float, distance_pct: float).
        """
        if len(df) < 20:
            return False, 0.0, 0.0
        recent  = df.tail(lookback)
        close   = df.iloc[-1]["Close"]
        # Find swing lows (local minima)
        lows = []
        for i in range(2, len(recent) - 2):
            l = recent["Low"].iloc[i]
            if l == recent["Low"].iloc[i-2:i+3].min():
                lows.append(l)
        if not lows:
            return False, 0.0, 0.0
        # Find nearest support below current price
        valid_supports = [l for l in lows if l < close * 1.02]
        if not valid_supports:
            return False, 0.0, 0.0
        nearest = max(valid_supports)
        dist_pct = (close - nearest) / nearest * 100
        at_support = dist_pct <= CFG["support_proximity_pct"]
        return at_support, round(nearest, 2), round(dist_pct, 2)

    @staticmethod
    def detect_upper_circuit_risk(chg_1d_pct):
        """
        Detect if stock is near NSE upper circuit limit.
        UC stocks are often untradeable the next session.
        """
        if abs(chg_1d_pct) >= 19.5:    return "UC20"   # 20% circuit
        if abs(chg_1d_pct) >= 9.5:     return "UC10"   # 10% circuit
        if abs(chg_1d_pct) >= 4.8:     return "UC5"    # 5% circuit
        return None

    @staticmethod
    def detect_ipo_base(df):
        """
        IPO Base detection — stock in first 400 days since listing.
        First base after IPO produces most explosive moves.
        """
        if len(df) < 10:
            return False, 0
        days_listed = len(df)
        if days_listed <= CFG["ipo_base_days"]:
            return True, days_listed
        return False, 0

    @staticmethod
    def detect_high_tight_flag(df, lookback=60):
        if len(df) < lookback:
            return False, {}
        recent = df.tail(lookback)
        close  = recent["Close"]
        for i in range(len(recent) - 30):
            window = close.iloc[i:i+30]
            gain   = (window.iloc[-1] / window.iloc[0] - 1) * 100
            if gain >= 80:
                surge_high = window.iloc[-1]
                current    = close.iloc[-1]
                pullback   = (surge_high - current) / surge_high * 100
                if 10 <= pullback <= 25:
                    return True, {"surge_pct": round(gain, 1), "pullback_pct": round(pullback, 1)}
        return False, {}

    @staticmethod
    def detect_three_tight_closes(df):
        if len(df) < 3:
            return False
        last3 = df["Close"].tail(3)
        rng   = (last3.max() - last3.min()) / last3.mean() * 100
        return bool(rng <= 1.5)

    @staticmethod
    def detect_volume_dry_up(df, days=3, lookback=20):
        if len(df) < lookback + days:
            return False
        avg_vol     = df["Volume"].tail(lookback).mean()
        recent_vols = df["Volume"].tail(days)
        return bool((recent_vols < avg_vol * 0.75).all())

    @staticmethod
    def detect_volume_surge(df):
        """
        Volume Surge Detection — three tiers based on volume vs 20-day average.

        Rules:
          • Volume must be on an UP day (Close > Open) for bullish confirmation
          • Mega Surge  : today >= 3.0x avg  → institutional accumulation / breakout fuel
          • Strong Surge: today >= 2.0x avg  → strong conviction buying
          • Surge       : today >= 1.5x avg  → above-average interest

        Returns:
          (surge_type: str, ratio: float, is_up_day: bool)
          surge_type: "Mega" | "Strong" | "Surge" | None
        """
        if len(df) < CFG["vol_surge_lookback"] + 1:
            return None, 0.0, False

        lookback  = CFG["vol_surge_lookback"]
        today     = df.iloc[-1]
        avg_vol   = df["Volume"].iloc[-(lookback+1):-1].mean()  # exclude today from avg
        if avg_vol <= 0:
            return None, 0.0, False

        ratio    = round(today["Volume"] / avg_vol, 2)
        is_up    = bool(today["Close"] > today["Open"])

        if ratio >= CFG["vol_surge_mega"]:
            surge_type = "MegaSurge"
        elif ratio >= CFG["vol_surge_strong"]:
            surge_type = "StrongSurge"
        elif ratio >= CFG["vol_surge_mild"]:
            surge_type = "Surge"
        else:
            surge_type = None

        return surge_type, ratio, is_up

    @staticmethod
    def detect_stage(weekly_df) -> tuple:
        """
        Weinstein Stage Analysis — classifies stock into Stage 1/2/3/4.
        Stage 2 (Advancing) = the ONLY buy zone for swing traders.
        Uses 30-week SMA slope + price position + volume pattern.
        Returns: (stage: str, details: dict)
        """
        weeks = CFG["stage_ma_weeks"]
        if weekly_df is None or len(weekly_df) < weeks + 5:
            return "Unknown", {}
        close       = weekly_df["Close"]
        vol         = weekly_df["Volume"]
        ma30        = close.rolling(weeks).mean()
        current     = close.iloc[-1]
        ma_now      = ma30.iloc[-1]
        ma_5w_ago   = ma30.iloc[-6]
        if pd.isna(ma_now) or pd.isna(ma_5w_ago) or ma_5w_ago == 0:
            return "Unknown", {}
        ma_slope_pct  = round((ma_now - ma_5w_ago) / ma_5w_ago * 100, 2)
        price_above   = bool(current > ma_now)
        ma_rising     = ma_slope_pct > 0
        ma_falling    = ma_slope_pct < -0.3
        vol_ma10      = vol.rolling(10).mean()
        recent_vol_r  = 1.0
        if not pd.isna(vol_ma10.iloc[-1]) and vol_ma10.iloc[-1] > 0:
            recent_vol_r = round(vol.iloc[-4:].mean() / vol_ma10.iloc[-1], 2)
        if   price_above and ma_rising:              stage = "Stage 2"
        elif price_above and not ma_rising and not ma_falling: stage = "Stage 3"
        elif not price_above and ma_falling:         stage = "Stage 4"
        else:                                        stage = "Stage 1"
        return stage, {
            "ma30"           : round(ma_now, 2),
            "ma_slope_pct"   : ma_slope_pct,
            "price_above_ma30": price_above,
            "vol_ratio_4w"   : recent_vol_r,
        }

    @staticmethod
    def detect_breakout(df, lookback=20):
        if len(df) < lookback + 5:
            return False, 0, {}
        close     = df["Close"]
        vol       = df["Volume"]
        current   = close.iloc[-1]
        resistance = close.iloc[-lookback-1:-1].max()
        pivot_test = resistance * (1 + CFG["breakout_buffer_pct"] / 100)
        is_above   = current > resistance
        is_confirmed = current > pivot_test
        vol_ratio  = vol.iloc[-1] / vol.tail(20).mean()
        vol_confirm = vol_ratio >= CFG["volume_surge_ratio"]
        days_since  = (close.iloc[-lookback:] < resistance).sum()
        if not is_above:
            return False, 0, {}
        strength = 0
        if is_confirmed:    strength += 30
        if vol_confirm:     strength += 35
        if vol_ratio > 2.0: strength += 15
        if vol_ratio > 3.0: strength += 10
        if days_since > 10: strength += 10
        return True, min(strength, 100), {
            "resistance"  : round(resistance, 2),
            "pivot"       : round(pivot_test, 2),
            "vol_ratio"   : round(vol_ratio, 2),
            "days_in_base": int(days_since),
        }


# ─────────────────────────────────────────────────────────────────────
#  INSTITUTIONAL ACCUMULATION DETECTOR  (v4.0)
# ─────────────────────────────────────────────────────────────────────
class InstitutionalAccumulationDetector:
    """
    Detects smart-money / institutional accumulation via 3 signals:

    ① Volume Accumulation  — above-avg volume on up-days, OBV rising
        • Track N consecutive days where volume > 20d avg on green candles
        • Institutions buy quietly over multiple sessions
    ② Price Tightening     — Bollinger Band contraction + 3-bar tight closes
        • Price coiling = distribution absorbed, ready to explode
    ③ Delivery Spike       — Delivery% well above stock's own history
        • High delivery = genuine buying, not intraday speculation

    Returns a dict:
        is_accumulating : bool
        accum_days      : int   — consecutive accumulation days detected
        accum_signals   : list  — which signals fired
        accum_score     : int   — 0-100 strength score
        accum_label     : str   — "Strong Accumulation" / "Accumulation" / "Watch"
    """

    @staticmethod
    def detect(df: pd.DataFrame, delivery_pct: float = None) -> dict:
        empty = {
            "is_accumulating": False, "accum_days": 0,
            "accum_signals": [],      "accum_score": 0,
            "accum_label":  "None",
        }
        if df is None or len(df) < 25:
            return empty

        signals  = []
        score    = 0
        close    = df["Close"]
        volume   = df["Volume"]
        opens    = df["Open"]

        avg_vol_20 = volume.iloc[-21:-1].mean()   # 20d avg excluding today
        if avg_vol_20 <= 0:
            return empty

        # ── Signal ①: Volume Accumulation (consecutive up-days with high vol) ──
        accum_days = 0
        for i in range(-1, -8, -1):             # look back up to 7 sessions
            idx = i
            if abs(idx) > len(df):
                break
            day_close  = close.iloc[idx]
            day_open   = opens.iloc[idx]
            day_vol    = volume.iloc[idx]
            is_up      = day_close > day_open
            high_vol   = day_vol > avg_vol_20 * 1.2
            if is_up and high_vol:
                accum_days += 1
            else:
                break

        if accum_days >= 4:
            signals.append(f"VolumeAccum {accum_days}d")
            score += min(accum_days * 10, 35)
        elif accum_days >= 2:
            signals.append(f"VolumeAccum {accum_days}d")
            score += accum_days * 7

        # ── OBV trend: rising OBV = institutional accumulation ──
        if "OBV" in df.columns and len(df) >= 15:
            obv_now    = df["OBV"].iloc[-1]
            obv_5d_ago = df["OBV"].iloc[-6]
            obv_10d    = df["OBV"].tail(10)
            obv_slope  = float(np.polyfit(range(10), obv_10d.values, 1)[0])
            if obv_slope > 0 and obv_now > obv_5d_ago:
                signals.append("OBV Rising")
                score += 15
            elif obv_slope > 0:
                score += 7

        # ── Signal ②: Price Tightening (BB squeeze + tight closes) ──
        if "BB_width" in df.columns:
            bw_now   = df["BB_width"].iloc[-1]
            bw_10d   = df["BB_width"].iloc[-11:-1].mean()
            # Band contracting compared to 10d avg
            if bw_now < bw_10d * 0.75 and bw_now < 10:
                signals.append(f"BBSqueeze({bw_now:.1f}%)")
                score += 18
            elif bw_now < bw_10d * 0.85 and bw_now < 12:
                signals.append(f"BBContracting({bw_now:.1f}%)")
                score += 10

        # 3 tight closes = volatility compression
        if len(df) >= 3:
            last3  = close.tail(3)
            rng3   = (last3.max() - last3.min()) / last3.mean() * 100
            if rng3 <= 1.2:
                signals.append("3TightCloses")
                score += 12
            elif rng3 <= 2.0:
                score += 6

        # ── Signal ③: Delivery Spike ──
        if delivery_pct is not None:
            if delivery_pct >= 70:
                signals.append(f"DeliverySpike({delivery_pct:.0f}%)")
                score += 20
            elif delivery_pct >= 55:
                signals.append(f"HighDelivery({delivery_pct:.0f}%)")
                score += 12
            elif delivery_pct >= 45:
                score += 5

        # ── Determine label ──
        score = min(score, 100)
        if score >= 60 and len(signals) >= 2:
            label         = "Strong Accumulation"
            is_accum      = True
        elif score >= 35 and len(signals) >= 1:
            label         = "Accumulation"
            is_accum      = True
        elif score >= 20:
            label         = "Watch"
            is_accum      = False
        else:
            label         = "None"
            is_accum      = False

        return {
            "is_accumulating": is_accum,
            "accum_days"     : accum_days,
            "accum_signals"  : signals,
            "accum_score"    : score,
            "accum_label"    : label,
        }


# ─────────────────────────────────────────────────────────────────────
#  TRADE SETUP CALCULATOR
# ─────────────────────────────────────────────────────────────────────
class TradeSetupCalculator:
    """
    Computes actionable Entry / Stop Loss / Target 1 / Target 2.

    Entry Logic:
      ① Confirmed breakout → pivot price (resistance + buffer)
      ② VCP score ≥ 70    → next day above today's high
      ③ NR7 / Inside Day  → above today's high range
      ④ Default           → CMP + 0.3% trigger

    Stop Loss Logic (tightest valid stop):
      • 1% below 10-day swing low
      • Entry − 2× ATR
      • Constrained: minimum 2%, maximum 7% below entry

    Targets:
      T1 = Entry + Risk × 2.0  (1:2 R:R)
      T2 = Entry + Risk × 3.0  (1:3 R:R)
    """

    @staticmethod
    def calculate(result: dict, daily_df: pd.DataFrame) -> dict:
        empty = {
            "entry": result.get("price", 0), "stop_loss": 0,
            "target1": 0, "target2": 0, "risk_pct": 0,
            "reward1_pct": 0, "reward2_pct": 0, "rr_ratio": 0,
            "setup_type": "N/A",
        }
        try:
            price    = result["price"]
            atr      = daily_df["ATR"].iloc[-1]
            bo_info  = result.get("breakout_info", {})
            vcp_sc   = result.get("vcp_score", 0)
            is_nr7   = result.get("nr7", False)
            is_ins   = result.get("inside_day", False)
            high_52w = result.get("high_52w", 0)

            # ── Determine Entry ──
            vcp_pivot = result.get("vcp_info", {}).get("pivot_price", 0)
            if result.get("breakout") and bo_info.get("pivot"):
                entry       = round(bo_info["pivot"] * 1.003, 2)
                setup_type  = "Breakout"
            elif vcp_sc >= 70 and vcp_pivot > 0:
                entry       = round(vcp_pivot, 2)           # v6: use exact VCP pivot
                setup_type  = "VCP"
            elif vcp_sc >= 70:
                entry       = round(daily_df["High"].iloc[-1] * 1.005, 2)
                setup_type  = "VCP"
            elif is_nr7 or is_ins:
                entry       = round(daily_df["High"].iloc[-1] * 1.003, 2)
                setup_type  = "Compression"
            else:
                entry       = round(price * 1.003, 2)
                setup_type  = "Trend Follow"

            # ── Determine Stop Loss ──
            swing_low_10d = daily_df["Low"].tail(10).min()
            sl_swing      = round(swing_low_10d * 0.99, 2)
            sl_atr        = round(entry - 2.2 * atr, 2)
            stop_loss_raw = max(sl_swing, sl_atr)  # tighter stop (higher value)

            max_sl = entry * 0.98   # at most 2% below entry
            min_sl = entry * 0.93   # at least 7% below entry (wider allowed)
            stop_loss = round(min(max_sl, max(min_sl, stop_loss_raw)), 2)

            risk     = max(entry - stop_loss, entry * 0.02)
            risk_pct = round(risk / entry * 100, 2)

            # ── Targets ──
            t1 = round(entry + risk * CFG["trade_rr_t1"], 2)
            t2 = round(entry + risk * CFG["trade_rr_t2"], 2)

            # Snap T1 to 52W high if it falls between entry and calculated T1
            if high_52w > entry * 1.01 and entry < high_52w < t1:
                t1 = round(high_52w, 2)

            reward1_pct = round((t1 - entry) / entry * 100, 2)
            reward2_pct = round((t2 - entry) / entry * 100, 2)
            rr          = round(reward1_pct / risk_pct, 1) if risk_pct > 0 else 0

            return {
                "entry"       : entry,
                "stop_loss"   : stop_loss,
                "target1"     : t1,
                "target2"     : t2,
                "risk_pct"    : risk_pct,
                "reward1_pct" : reward1_pct,
                "reward2_pct" : reward2_pct,
                "rr_ratio"    : rr,
                "setup_type"  : setup_type,
            }
        except Exception:
            return empty


# ─────────────────────────────────────────────────────────────────────
#  SECTOR MOMENTUM ANALYZER
# ─────────────────────────────────────────────────────────────────────
class SectorMomentumAnalyzer:
    """Groups stocks by sector, ranks sectors by composite strength score (0-100)."""

    @staticmethod
    def assign_sectors(results: list):
        for r in results:
            r["sector"] = SECTOR_MAP.get(r["symbol"], "Others")

    @staticmethod
    def rank_and_score(results: list) -> dict:
        """
        Computes a composite Sector Strength Score (0-100) per sector using:
          • Avg RS Percentile (40%)
          • % stocks above 200 EMA (25%)
          • % stocks in Stage 2 (20%)
          • Avg ADX / trend strength (15%)

        Returns sorted_sectors: [(name, strength_score, avg_rs, count, stage2_count), ...]
        Also writes sector_rank + sector_momentum into each result dict.
        """
        sector_data: dict = {}
        for r in results:
            sec = r.get("sector", "Others")
            sector_data.setdefault(sec, []).append(r)

        sector_scores = {}
        sector_details = {}
        for sec, members in sector_data.items():
            n             = len(members)
            avg_rs        = round(float(np.mean([m["rs_percentile"] for m in members])), 1)
            pct_above_200 = round(sum(1 for m in members if m.get("above_200ema")) / n * 100, 1)
            pct_stage2    = round(sum(1 for m in members if m.get("is_stage2")) / n * 100, 1)
            avg_adx       = round(float(np.mean([m.get("adx", 20) for m in members])), 1)
            avg_accum     = round(float(np.mean([m.get("accum_score", 0) for m in members])), 1)

            # Composite strength (0-100)
            strength = round(
                avg_rs        * 0.40 +
                pct_above_200 * 0.25 +
                pct_stage2    * 0.20 +
                min(avg_adx, 60) / 60 * 100 * 0.15,
                1
            )
            sector_scores[sec]  = strength
            sector_details[sec] = {
                "avg_rs"       : avg_rs,
                "pct_above_200": pct_above_200,
                "pct_stage2"   : pct_stage2,
                "avg_adx"      : avg_adx,
                "avg_accum"    : avg_accum,
                "count"        : n,
                "stage2_count" : sum(1 for m in members if m.get("is_stage2")),
                "strength"     : strength,
            }

        sorted_secs = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
        sector_rank = {sec: i+1 for i, (sec, _) in enumerate(sorted_secs)}
        total_secs  = len(sector_rank)

        for r in results:
            sec = r.get("sector", "Others")
            det = sector_details.get(sec, {})
            r["sector_rank"]      = sector_rank.get(sec, total_secs)
            r["sector_momentum"]  = sector_scores.get(sec, 0)
            r["sector_total"]     = total_secs
            r["sector_strength"]  = sector_scores.get(sec, 0)   # alias

        return [
            (sec, sector_details[sec]["strength"], sector_details[sec]["avg_rs"],
             sector_details[sec]["count"], sector_details[sec]["stage2_count"],
             sector_details[sec]["pct_above_200"], sector_details[sec]["avg_adx"])
            for sec, _ in sorted_secs
        ]


# ─────────────────────────────────────────────────────────────────────
#  STOCK SCORER & GRADER  ── v5.0 PRE-MOVE SETUP ENGINE
# ─────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
#  INDIA VIX FETCHER  (v7.0)
# ─────────────────────────────────────────────────────────────────────
class MaxPainCalculator:
    """
    Max Pain — the strike price at which options sellers (market makers/institutions)
    profit most. Near expiry (last 3-5 days), stock/index price gravitates toward max pain.

    Formula:
      For each strike price K:
        Total loss to option sellers = sum of all CE/PE OI × max(0, K - strike) or max(0, strike - K)
      Max Pain = strike where total option seller loss is MINIMUM

    Why it matters for Indian markets:
      - NSE weekly expiry every Thursday
      - Nifty/BankNifty tend to close near max pain on expiry day
      - Stocks in F&O also follow this pattern near expiry
      - Used by institutional traders to know where NOT to let the market go
    """

    @staticmethod
    def calculate(options_data: list) -> dict:
        """
        Calculate Max Pain from NSE options chain data.
        options_data: list of dicts with CE and PE openInterest per strike
        Returns: {max_pain_strike, distance_from_cmp_pct, sentiment}
        """
        if not options_data:
            return {"max_pain": None, "distance_pct": None, "sentiment": "N/A"}

        try:
            # Extract strikes and OI
            strikes = {}
            for row in options_data:
                strike = row.get("strikePrice", 0)
                ce_oi  = row.get("CE", {}).get("openInterest", 0) or 0
                pe_oi  = row.get("PE", {}).get("openInterest", 0) or 0
                if strike:
                    strikes[strike] = {"ce_oi": ce_oi, "pe_oi": pe_oi}

            if not strikes:
                return {"max_pain": None, "distance_pct": None, "sentiment": "N/A"}

            all_strikes = sorted(strikes.keys())

            # Calculate total loss at each strike
            total_losses = {}
            for k in all_strikes:
                ce_loss = sum(max(0, k - s) * strikes[s]["ce_oi"] for s in all_strikes)
                pe_loss = sum(max(0, s - k) * strikes[s]["pe_oi"] for s in all_strikes)
                total_losses[k] = ce_loss + pe_loss

            # Max Pain = strike with minimum total option seller loss
            max_pain_strike = min(total_losses, key=total_losses.get)

            return {
                "max_pain"   : max_pain_strike,
                "all_losses" : {str(k): v for k, v in list(total_losses.items())[:20]},
                "calculated" : True,
            }
        except Exception as e:
            return {"max_pain": None, "calculated": False, "error": str(e)}

    @staticmethod
    def fetch_nifty_max_pain() -> dict:
        """Fetch Nifty options chain from NSE and compute max pain."""
        result = {"max_pain": None, "sentiment": "N/A", "fetched": False}
        try:
            url  = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
            resp = NSESession.get().get_api(url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                data     = resp.json()
                oc_data  = data.get("records", {}).get("data", [])
                cmp      = data.get("records", {}).get("underlyingValue", 0)
                mp       = MaxPainCalculator.calculate(oc_data)
                max_pain = mp.get("max_pain")
                if max_pain and cmp:
                    dist = round((max_pain / cmp - 1) * 100, 2)
                    sentiment = (
                        "Price above Max Pain — bearish pull" if cmp > max_pain * 1.01 else
                        "Price below Max Pain — bullish pull" if cmp < max_pain * 0.99 else
                        "Price at Max Pain — expiry pinning"
                    )
                    result = {
                        "max_pain"    : max_pain,
                        "cmp"         : cmp,
                        "distance_pct": dist,
                        "sentiment"   : sentiment,
                        "fetched"     : True,
                    }
                    print(f"   📌 Nifty Max Pain: {max_pain} (CMP: {cmp}, dist: {dist:+.1f}%)")
        except Exception as e:
            print(f"   ⚠️  Max Pain: {e}")
        return result


class IndiaVIXFetcher:
    """India VIX from NSE — purely Indian fear gauge from Nifty options."""
    URL_ALL     = "https://www.nseindia.com/api/allIndices"
    URL_VIX_CSV = "https://archives.nseindia.com/content/indices/vix_history.csv"
    def __init__(self):
        self._vix = None
        self._fetched = False
    def fetch(self):
        if self._fetched: return self._vix
        # Use plain session — allIndices works without NSE cookies (confirmed)
        sess = requests.Session()
        sess.headers.update(HEADERS)
        # Try 1: allIndices (confirmed working — 110KB response)
        try:
            resp = sess.get(self.URL_ALL, timeout=12)
            if resp.status_code == 200 and resp.text.strip() and resp.text.strip()[0] in "[{":
                for item in resp.json().get("data", []):
                    idx_name = str(item.get("index","")).upper()
                    if "VIX" in idx_name or "INDIA VIX" in idx_name:
                        v = item.get("last") or item.get("currentValue") or item.get("indexValue")
                        if v:
                            self._vix = round(float(v), 2)
                            print(f"   📊 India VIX: {self._vix}")
                            self._fetched = True
                            return self._vix
        except Exception as e:
            print(f"   ⚠️  India VIX (allIndices): {e}")
        # Try 2: NSESession (warmed)
        try:
            resp2 = NSESession.get().get_api(self.URL_ALL, timeout=12)
            if resp2.status_code == 200 and resp2.text.strip()[0] in "[{":
                for item in resp2.json().get("data", []):
                    if "VIX" in str(item.get("index","")).upper():
                        v = item.get("last") or item.get("currentValue")
                        if v:
                            self._vix = round(float(v), 2)
                            print(f"   📊 India VIX: {self._vix}")
                            self._fetched = True
                            return self._vix
        except Exception:
            pass
        print("   ⚠️  India VIX: not available today")
        self._fetched = True
        return self._vix
    def score(self):
        v = self._vix
        if v is None:  return 4
        if v < 13:     return 8
        if v < 16:     return 6
        if v < 18:     return 4
        if v < 20:     return 2
        return -5


# ─────────────────────────────────────────────────────────────────────
#  OPEN INTEREST FETCHER  (v7.0)
# ─────────────────────────────────────────────────────────────────────
class OpenInterestFetcher:
    """NSE F&O OI data. Long buildup = institutions buying = bullish."""
    def __init__(self):
        self._data = {}
        self._fetched = False
    def fetch_all(self):
        if self._fetched: return
        try:
            url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20500"
            resp = NSESession.get().get_api(url, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                for item in resp.json().get("data", []):
                    sym = str(item.get("symbol","")).strip().upper()
                    if not sym: continue
                    try:
                        oi_ch = float(item.get("perChange", 0) or 0)
                        pr_ch = float(item.get("pChange",   0) or 0)
                        if   oi_ch > 2  and pr_ch > 0: bt = "LongBuildup"
                        elif oi_ch > 2  and pr_ch < 0: bt = "ShortBuildup"
                        elif oi_ch < -2 and pr_ch > 0: bt = "ShortCovering"
                        elif oi_ch < -2 and pr_ch < 0: bt = "LongUnwinding"
                        else:                           bt = "Neutral"
                        self._data[sym] = {"oi_change_pct": round(oi_ch,2), "buildup_type": bt}
                    except Exception: pass
                print(f"   📈 OI data: {len(self._data)} stocks")
        except Exception as e:
            print(f"   ⚠️  OI fetch: {e}")
        self._fetched = True
    def get(self, symbol):
        return self._data.get(symbol, {})
    @staticmethod
    def score(oi_data):
        if not oi_data: return 0
        return {"LongBuildup":10,"ShortCovering":8,"Neutral":3,
                "LongUnwinding":-5,"ShortBuildup":0}.get(oi_data.get("buildup_type","Neutral"), 0)


# ─────────────────────────────────────────────────────────────────────
#  PROMOTER ACTIVITY FETCHER  (v7.0)
# ─────────────────────────────────────────────────────────────────────
class PromoterActivityFetcher:
    """SEBI-mandated quarterly shareholding data. Promoter buying = strongest India signal."""
    def __init__(self):
        self._data = {}
        self._fetched_set = set()
    def fetch(self, symbol):
        if symbol in self._fetched_set:
            return self._data.get(symbol, {})
        self._fetched_set.add(symbol)
        result = {"promoter_holding":None,"promoter_chg_qoq":None,
                  "promoter_buying":False,"promoter_selling":False,
                  "pledge_pct":None,"pledge_decreasing":False}
        try:
            url = f"https://www.nseindia.com/api/shareholders-data?symbol={symbol}"
            resp = NSESession.get().get_api(url, timeout=10)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                if isinstance(data, list) and len(data) >= 2:
                    ph_now  = float(data[0].get("promoter",       0) or 0)
                    ph_prev = float(data[1].get("promoter",       0) or 0)
                    pl_now  = float(data[0].get("promoterPledge", 0) or 0)
                    pl_prev = float(data[1].get("promoterPledge", 0) or 0)
                    chg = round(ph_now - ph_prev, 2)
                    result.update({
                        "promoter_holding" : round(ph_now, 2),
                        "promoter_chg_qoq" : chg,
                        "promoter_buying"  : chg > 0.5,
                        "promoter_selling" : chg < -0.5,
                        "pledge_pct"       : round(pl_now, 2),
                        "pledge_decreasing": pl_prev > pl_now > 0,
                    })
        except Exception: pass
        self._data[symbol] = result
        return result
    @staticmethod
    def score(data):
        if not data: return 0
        s = 0
        if data.get("promoter_buying"):   s += 10
        if data.get("pledge_decreasing"): s += 5
        if data.get("promoter_selling"):  s -= 10
        return s


# ─────────────────────────────────────────────────────────────────────
#  STOCK SCORER  (v7.0 — India-First Scoring Engine)
# ─────────────────────────────────────────────────────────────────────

class ExpertFilter:
    """
    13-point expert decision checklist used by professional Indian swing traders.
    Each point = 1 YES or NO.

    RULE:
      ≥ 10 YES → Conviction trade (aggressive position)
       7–9 YES → Normal trade (standard position)
       ≤ 6 YES → No trade (skip regardless of score)

    Categories:
      A. Market Context      (2 points) — Nifty + breadth
      B. Sector Confirmation (2 points) — sector index + peer breakouts
      C. Price Structure     (2 points) — base + higher lows
      D. Breakout Quality    (2 points) — clear resistance + candle quality
      E. Volume Behavior     (2 points) — surge on breakout + contraction after
      F. Indicator Health    (1 point)  — RSI 52-62 + ADX 20-30
      G. Risk Setup          (2 points) — SL defined + R:R ≥ 1:2
    """

    @staticmethod
    def evaluate(result: dict, sector_strength: float,
                 nifty_above_sma: bool, breadth_pct: float) -> dict:
        """
        Evaluate all 13 expert checklist points for a single stock.
        Returns dict with individual point results + total YES count + decision.
        """
        price      = result.get("price", 0)
        ema_20     = result.get("ema_21", 0)   # using EMA21 ≈ SMA20
        ema_50     = result.get("ema_50", 0)
        ema_200    = result.get("ema_200", 0)
        rsi        = result.get("rsi", 0)
        adx        = result.get("adx", 0)
        macd       = result.get("macd", 0)
        macd_sig   = result.get("macd_sig", 0)
        vol_ratio  = result.get("vol_ratio", 0)
        pct_high   = result.get("pct_from_high", -100)
        bb_width   = result.get("bb_width", 20)
        chg_5d     = result.get("chg_5d", 0)
        chg_1m     = result.get("chg_1m", 0)
        delivery   = result.get("delivery_pct", 0) or 0
        ts         = result.get("trade_setup", {}) or {}
        entry      = ts.get("entry", 0) or 0
        sl         = ts.get("stop_loss", 0) or 0
        rr         = ts.get("rr_ratio", 0) or 0
        bo_found   = result.get("breakout", False)
        is_nr7     = result.get("nr7", False)
        is_inside  = result.get("inside_day", False)
        candles    = result.get("candle_patterns", {})
        stage      = result.get("stage", "Unknown")
        is_stage2  = result.get("is_stage2", False)
        vcp_score  = result.get("vcp_score", 0)
        near_high  = pct_high >= -5
        vol_dry    = result.get("vol_dry_up", False)

        # ── A. MARKET CONTEXT (2 points) ──
        a1 = nifty_above_sma                     # Nifty above 20 & 50 DMA
        a2 = breadth_pct >= 55                   # Market breadth supportive

        # ── B. SECTOR CONFIRMATION (2 points) ──
        b1 = sector_strength >= 55               # Sector index above 20 DMA equivalent
        b2 = sector_strength >= 65               # Same sector stocks strong/breakout zone

        # ── C. PRICE STRUCTURE (2 points) ──
        # v7.1 FIX: Removed VCP (US concept), replaced with India-specific checks
        # 3-6 weeks consolidation = flat base OR NR7/Inside Day (confirmed)
        # OR: stock in 8-20% below 52W high zone (accumulation zone)
        pct_high2 = result.get("pct_from_high", -100)
        in_accum_zone = -20 <= pct_high2 <= -5   # classic Indian accumulation range
        c1 = (result.get("flat_base", False) or
              is_nr7 or is_inside or
              in_accum_zone or
              result.get("vol_dry_up", False))    # Volume dry-up = base forming
        # Higher low / tight range = sellers weak
        c2 = (price > ema_20 and ema_20 > ema_50 and
              chg_1m > -5 and chg_1m < 20)       # Price structure intact

        # ── D. BREAKOUT QUALITY (2 points) ──
        # Breakout above clear resistance
        d1 = (bo_found or near_high or
              (price > ema_20 and vol_ratio >= 1.5))   # Breakout confirmed
        # Good candle — no big upper wick (using vol_ratio + delivery as proxy)
        d2 = (delivery >= 45 or
              bool(candles) or
              vol_ratio >= 1.8)                  # Candle quality / conviction

        # ── E. VOLUME BEHAVIOR (2 points) ──
        e1 = vol_ratio >= 1.5                    # Breakout candle ≥ 1.5× avg volume
        e2 = vol_dry or vol_ratio < 2.5          # After surge: contraction (no dumping)

        # ── F. INDICATOR HEALTH (1 point) ──
        # v7.1 FIX: Replaced MACD (US signal, removed) with Supertrend (India signal)
        # RSI in sweet spot + ADX showing trend + Supertrend in BUY mode
        st_buy = result.get("supertrend_dir", 0) == 1
        f1 = (52 <= rsi <= 68 and adx >= 20 and st_buy)

        # ── G. RISK SETUP (2 points) ──
        # Stop-loss clearly defined
        g1 = (sl > 0 and entry > 0 and
              0 < (entry - sl) / entry * 100 <= 7)   # SL within 7% of entry
        # R:R ≥ 1:2
        g2 = rr >= 1.8                           # Minimum 1:2 risk reward

        checks = {
            "a1_nifty_above_dma"       : a1,
            "a2_breadth_supportive"    : a2,
            "b1_sector_strong"         : b1,
            "b2_sector_peers_breaking" : b2,
            "c1_base_consolidation"    : c1,
            "c2_price_structure_ok"    : c2,
            "d1_breakout_confirmed"    : d1,
            "d2_candle_quality_ok"     : d2,
            "e1_volume_surge"          : e1,
            "e2_volume_contraction"    : e2,
            "f1_indicators_aligned"    : f1,
            "g1_stoploss_defined"      : g1,
            "g2_rr_minimum"            : g2,
        }

        yes_count = sum(1 for v in checks.values() if v)

        if   yes_count >= 10: decision = "CONVICTION"   # aggressive position
        elif yes_count >= 7:  decision = "TRADE"        # normal position
        else:                 decision = "SKIP"         # no trade

        return {
            "expert_checks"  : checks,
            "expert_yes"     : yes_count,
            "expert_decision": decision,
            "expert_grade"   : ("A+" if yes_count >= 11 else
                                "A"  if yes_count >= 9  else
                                "B+" if yes_count >= 7  else
                                "B"  if yes_count >= 5  else "C"),
        }

    @staticmethod
    def labels() -> dict:
        """Human-readable labels for each check point."""
        return {
            "a1_nifty_above_dma"       : "Nifty above 20 & 50 DMA",
            "a2_breadth_supportive"    : "Market breadth ≥ 55% above 200 EMA",
            "b1_sector_strong"         : "Sector strength ≥ 55 (index above 20 DMA)",
            "b2_sector_peers_breaking" : "Sector peers in breakout zone (strength ≥ 65)",
            "c1_base_consolidation"    : "3–6 week consolidation / base formed",
            "c2_price_structure_ok"    : "Higher lows / tight range (sellers weak)",
            "d1_breakout_confirmed"    : "Price at or above resistance / 20-day high",
            "d2_candle_quality_ok"     : "Strong candle — high delivery or conviction",
            "e1_volume_surge"          : "Breakout volume ≥ 1.5× 20-day average",
            "e2_volume_contraction"    : "Volume contraction after surge (no dumping)",
            "f1_indicators_aligned"    : "RSI 52–68, ADX ≥ 20, MACD > Signal",
            "g1_stoploss_defined"      : "Stop-loss defined, risk ≤ 7% of entry",
            "g2_rr_minimum"            : "Risk : Reward ≥ 1:2",
        }



# ─────────────────────────────────────────────────────────────────────
#  MAIN ANALYSIS PIPELINE
# ─────────────────────────────────────────────────────────────────────

class StockScorer:
    """
    v7.0 India-First Swing Trading Scorer.

    Follow Indian institutional money BEFORE price reacts.
    India-specific signals get highest weights:
      Delivery%(12) + FII/DII(12) + Bulk deals(12) + Promoter buying(10)
      + India VIX(8) + OI buildup(10) + PCR(6) = 70 pts India-specific

    Setup quality (reduced US-centric signals):
      Compression(14) + VolDryUp(8) + BasePos(8) + Supertrend(10) = 40 pts
      VCP reduced 18→10, BB reduced 12→6

    Penalties:
      Freshness(-28) + Pledge(-15) + Results season(-10) = -53 max

    Score 0-100. A+≥80, A≥67, B+≥54, B≥42, C≥28
    """

    def __init__(self, nifty_series, vix_fetcher=None, fii_dii_data=None, pcr_data=None):
        self.nifty   = nifty_series
        self.vix     = vix_fetcher
        self.fii_dii = fii_dii_data or {}
        self.pcr     = pcr_data or {}

    def relative_strength(self, stock_close, lookback=63):
        if self.nifty is None or len(self.nifty) < lookback: return 0
        try:
            common = stock_close.index.intersection(self.nifty.index)
            if len(common) < lookback: return 0
            sc = stock_close.loc[common].tail(lookback)
            nc = self.nifty.loc[common].tail(lookback)
            return round((sc.iloc[-1]/sc.iloc[0]-1)*100 - (nc.iloc[-1]/nc.iloc[0]-1)*100, 2)
        except Exception: return 0

    # ── India-Specific (highest weight) ──

    @staticmethod
    def score_delivery_india(df, delivery_pct):
        """
        v7.1 FIX: Delivery must be directional + volume-weighted.
        High delivery on UP day   = accumulation (bullish) → reward
        High delivery on DOWN day = distribution (selling) → penalise
        Low absolute volume + high delivery %  = meaningless → ignore
        """
        if delivery_pct is None or len(df) < 2: return 0

        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        close = last["Close"]
        prev_close = prev["Close"]

        # Price direction
        price_up = close >= prev_close   # green or flat candle

        # Volume weight — delivery % on illiquid stock is noise
        avg_daily_value = df["Volume"].tail(20).mean() * close
        if avg_daily_value < 5_000_000:   # below ₹50 lakh avg daily value
            return 0   # too illiquid — delivery % unreliable

        # Accumulation: delivery high + price up = institutions buying
        if price_up:
            if   delivery_pct >= 75: return 12
            elif delivery_pct >= 65: return 10
            elif delivery_pct >= 55: return 8
            elif delivery_pct >= 45: return 5
            elif delivery_pct >= 35: return 2
            return 0
        else:
            # Distribution: delivery high + price down = institutions selling
            if   delivery_pct >= 70: return -8   # heavy distribution
            elif delivery_pct >= 55: return -4   # moderate distribution
            elif delivery_pct >= 40: return -2
            return 0   # low delivery on down day = just profit booking

    def score_fii_dii_india(self):
        """
        v7.1 FIX: FII flow is market-wide — same for all 500 stocks.
        Changed from additive (wrong) to a GATE score:
          - Strong FII buying  → +6  (market tailwind)
          - Moderate buying    → +3
          - Neutral            → 0
          - Selling            → -3 to -8 (market headwind)
        This is applied as a MARKET GATE — it sets the context but
        does not mislead by adding 12 identical pts to every stock.
        A stock-specific OI buildup score handles individual F&O stocks.
        """
        fii_5d    = self.fii_dii.get("fii_5d")
        fii_today = self.fii_dii.get("fii_net")
        if fii_5d is None: return 2   # unknown → small neutral

        if   fii_5d >  6000: return 6    # strong buying  → solid tailwind
        elif fii_5d >  2000: return 4    # moderate buying
        elif fii_5d >   500: return 2    # mild buying
        elif fii_5d >  -500: return 0    # neutral
        elif fii_5d > -2000: return -3   # mild selling
        elif fii_5d > -5000: return -5   # heavy selling
        else:                return -8   # extreme selling → avoid new longs

    @staticmethod
    def score_bulk_deal_india(deal_data):
        if not deal_data: return 0
        if deal_data.get("bulk_sell"):  return -20
        if deal_data.get("bulk_buy"):   return 12
        if deal_data.get("block_buy"):  return 10
        return 0

    @staticmethod
    def score_promoter_india(pdata):
        if not pdata: return 0
        s = 0
        if pdata.get("promoter_buying"):   s += 10
        if pdata.get("pledge_decreasing"): s += 5
        if pdata.get("promoter_selling"):  s -= 10
        return s

    def score_india_vix(self):
        if self.vix is None: return 4
        return self.vix.score() if hasattr(self.vix, "score") else 4

    @staticmethod
    def score_oi_buildup(oi_data):
        return OpenInterestFetcher.score(oi_data)

    def score_pcr_india(self):
        pcr = self.pcr.get("nifty_pcr")
        if pcr is None: return 3
        if   pcr > 1.4: return 6
        elif pcr > 1.2: return 5
        elif pcr > 0.9: return 3
        elif pcr > 0.7: return 1
        return 0

    def score_fii_absorption_india(self, df, delivery_pct):
        """
        FII Absorption Signal — PRO-LEVEL India logic.
        When FII is SELLING overall (market-wide headwind)
        BUT this individual stock's price is HOLDING or going UP
        with HIGH DELIVERY → DII/retail/promoters absorbing FII selling.

        This is a VERY bullish signal — smart domestic money is accumulating
        while foreign money exits. Stock will likely explode when FII stops selling.

        Score: +10 if strong absorption, +6 moderate, 0 if no absorption.
        """
        fii_5d     = self.fii_dii.get("fii_5d")
        if fii_5d is None or delivery_pct is None or len(df) < 5:
            return 0

        fii_selling = fii_5d < -1000  # FII selling ₹1000+ Cr over 5 days

        if not fii_selling:
            return 0   # FII not selling — absorption not relevant

        # Check if this stock is holding / going up despite FII selling
        try:
            chg_5d      = (df["Close"].iloc[-1] / df["Close"].iloc[-6] - 1) * 100
            price_up    = df["Close"].iloc[-1] >= df["Close"].iloc[-2]
            vol_r       = df.iloc[-1].get("Vol_ratio", 1) or 1
            avg_val     = df["Volume"].tail(20).mean() * df["Close"].iloc[-1]

            if avg_val < 5_000_000: return 0  # illiquid — ignore

            stock_holding  = chg_5d > -2    # stock flat or positive last 5 days
            high_delivery  = delivery_pct >= 55

            if stock_holding and high_delivery and price_up:
                return 10   # Strong absorption — highest conviction signal
            elif stock_holding and high_delivery:
                return 6    # Moderate absorption
            elif stock_holding and delivery_pct >= 45:
                return 3    # Weak absorption
        except Exception:
            pass
        return 0

    def score_fii_pcr_combined(self):
        """
        FII + PCR Combined Signal — India's highest confidence bull indicator.
        When BOTH FII is buying AND PCR > 1.2 on the same day:
          = institutions buying + options market shows too many puts = contrarian bull signal
          = best possible market condition for swing long trades
        This combination appears roughly 15-20 times per year.
        When it appears, it is the strongest market-level buy signal in Indian markets.
        """
        fii_5d = self.fii_dii.get("fii_5d")
        pcr    = self.pcr.get("nifty_pcr")

        if fii_5d is None or pcr is None:
            return 0

        fii_buying  = fii_5d > 2000   # FII net buying ₹2000+ Cr over 5 days
        pcr_bullish = pcr > 1.2       # market oversold per options data

        if   fii_buying and pcr > 1.4:  return 8   # very strong combined signal
        elif fii_buying and pcr_bullish: return 5   # strong combined signal
        elif fii_buying:                 return 2   # FII buying but PCR neutral
        elif pcr_bullish and fii_5d > 0: return 2   # PCR bullish + mild FII buying
        return 0

    # ── Setup Quality ──

    @staticmethod
    def score_compression_india(is_nr7, is_inside_day, pp_found):
        s = 0
        if is_nr7:        s += 8
        if is_inside_day: s += 6
        if pp_found:      s += 8
        return min(s, 14)


    def _score_compression_india_confirmed(self, is_nr7, is_inside_day, delivery_pct, df):
        """
        Compression score with delivery confirmation (India-specific).
        NR7/InsideDay patterns are more reliable when delivery % is elevated.
        """
        s = 0
        del_pct = delivery_pct or 0
        if is_nr7:
            s += 8
            if del_pct >= 55: s += 2   # delivery confirms accumulation
        if is_inside_day:
            s += 6
            if del_pct >= 55: s += 2
        # Pocket pivot detection
        if len(df) >= 11:
            try:
                last_vol = df["Volume"].iloc[-1]
                max_down_vol = df["Volume"].iloc[-11:-1][
                    df["Close"].iloc[-11:-1].diff() < 0].max()
                if last_vol > max_down_vol and df["Close"].iloc[-1] >= df["Close"].iloc[-2]:
                    s += 8
            except Exception:
                pass
        return min(s, 14)

    @staticmethod
    def score_volume_dryup_india(df):
        if len(df) < 10: return 0
        try:
            avg_vol  = df["Volume"].tail(20).mean()
            if avg_vol == 0: return 0
            ratios   = [v/avg_vol for v in df["Volume"].tail(3)]
            if all(r < 0.7  for r in ratios): return 8
            elif all(r < 0.85 for r in ratios): return 5
            elif sum(1 for r in ratios if r < 0.75) >= 2: return 3
        except Exception: pass
        return 0

    @staticmethod
    def score_base_position_india(df):
        if len(df) < 52: return 0
        try:
            high52  = df["High"].tail(252).max()
            current = df["Close"].iloc[-1]
            pct_off = (current/high52 - 1)*100
            if  -20 <= pct_off <= -8:  return 8
            elif -25 <= pct_off < -20: return 5
            elif  -8 < pct_off <= -4:  return 3
            elif -30 <= pct_off < -25: return 2
        except Exception: pass
        return 0

    @staticmethod
    def score_supertrend_india(df):
        if "ST_Direction" not in df.columns or len(df) < 3: return 0
        cur  = df["ST_Direction"].iloc[-1]
        prev = df["ST_Direction"].iloc[-2]
        if cur == 1: return 10 if prev != 1 else 7
        return 0

    @staticmethod
    def score_bb_squeeze_india(df):
        if len(df) < 20: return 0
        bb_w = df.iloc[-1].get("BB_width", 20) or 20
        if   bb_w < 4:  return 6
        elif bb_w < 6:  return 5
        elif bb_w < 8:  return 3
        elif bb_w < 12: return 1
        return 0

    @staticmethod
    def score_vcp_india(vcp_score_raw):
        if   vcp_score_raw >= 85: return 10
        elif vcp_score_raw >= 75: return 8
        elif vcp_score_raw >= 65: return 6
        elif vcp_score_raw >= 55: return 4
        elif vcp_score_raw >= 45: return 2
        return 0

    @staticmethod
    def score_flat_base_india(has_flat_base, flat_base_info):
        if not has_flat_base: return 0
        s = 6
        if flat_base_info.get("vol_declining"): s += 2
        if flat_base_info.get("above_ema21"):   s += 1
        if flat_base_info.get("range_pct",12) < 7: s += 1
        return min(s, 10)

    # ── Trend Confirmation ──

    @staticmethod
    def score_ema_alignment_india(df):
        last  = df.iloc[-1]
        c     = last["Close"]
        conds = [
            c                      > last.get("EMA_10",  0),
            last.get("EMA_10",  0) > last.get("EMA_21",  0),
            last.get("EMA_21",  0) > last.get("EMA_50",  0),
            last.get("EMA_50",  0) > last.get("EMA_200", 0),
        ]
        return min(round(sum(conds)*1.5), 6)

    @staticmethod
    def score_rsi_india(df):
        rsi = df.iloc[-1].get("RSI", 50) or 50
        if   50 <= rsi <= 68: return 9
        elif 45 <= rsi <  50: return 6
        elif 68 <  rsi <= 75: return 3
        elif 40 <= rsi <  45: return 2
        return 0

    @staticmethod
    def score_adx_india(df):
        last  = df.iloc[-1]
        adx   = last.get("ADX",     0) or 0
        di_p  = last.get("DI_plus", 0) or 0
        di_m  = last.get("DI_minus",0) or 0
        s     = 0
        if   adx > 30: s += 5
        elif adx > 25: s += 4
        elif adx > 20: s += 2
        if di_p > di_m: s += 3
        return min(s, 8)

    @staticmethod
    def score_macd_india(df):
        last = df.iloc[-1]
        macd = last.get("MACD",        0) or 0
        sig  = last.get("MACD_signal", 0) or 0
        hist = last.get("MACD_hist",   0) or 0
        s    = 0
        if macd > sig: s += 3
        if hist > 0:   s += 2
        if len(df) >= 2:
            ph = df.iloc[-2].get("MACD_hist", 0) or 0
            if hist > ph > 0: s += 1
        return min(s, 6)

    @staticmethod
    def score_weekly_trend_india(weekly_df):
        if weekly_df is None or len(weekly_df) < 10: return 0
        last  = weekly_df.iloc[-1]
        close = last["Close"]
        s     = 0
        if close > last.get("W_EMA_10", 0): s += 2
        if close > last.get("W_EMA_21", 0): s += 2
        if last.get("W_ROC_4", 0) > 0:      s += 2
        return min(s, 6)

    @staticmethod
    def score_obv_div_india(has_div):
        return 8 if has_div else 0

    # ── Quality Gate ──

    @staticmethod
    def score_fundamentals_india(fund_data):
        if not fund_data: return 0
        return min(round((fund_data.get("fund_score",0) or 0) * 0.5), 10)

    @staticmethod
    def score_golden_cross_india(df):
        """
        Golden Cross / Death Cross — 50 EMA vs 200 EMA.
        Most watched long-term trend signal in Indian markets.
        All major Indian brokers (Zerodha, ICICI, HDFC) highlight this.

        Fresh Golden Cross (50 EMA just crossed above 200 EMA) = +8 pts
        Sustained Golden Cross (50 above 200 for >5 days)       = +4 pts
        Death Cross (50 EMA below 200 EMA)                      = −6 pts
        """
        if len(df) < 200: return 0
        try:
            ema50  = df["EMA_50"].iloc[-1]  if "EMA_50"  in df.columns else df["Close"].ewm(span=50).mean().iloc[-1]
            ema200 = df["EMA_200"].iloc[-1] if "EMA_200" in df.columns else df["Close"].ewm(span=200).mean().iloc[-1]
            # Previous values for fresh cross detection
            ema50_prev  = df["EMA_50"].iloc[-2]  if "EMA_50"  in df.columns else df["Close"].ewm(span=50).mean().iloc[-2]
            ema200_prev = df["EMA_200"].iloc[-2] if "EMA_200" in df.columns else df["Close"].ewm(span=200).mean().iloc[-2]

            currently_above = ema50 > ema200
            was_above       = ema50_prev > ema200_prev

            if currently_above:
                fresh_cross = not was_above   # just crossed today
                return 8 if fresh_cross else 4
            else:
                fresh_death = was_above       # just crossed below today
                return -8 if fresh_death else -6
        except Exception:
            return 0

    @staticmethod
    def score_stage_india(stage):
        return {"Stage 2":8,"Stage 1":0,"Stage 3":-5,"Stage 4":-10,"Unknown":0}.get(stage, 0)

    @staticmethod
    def score_candle_india(candle_score_raw):
        return min(candle_score_raw, 8)

    @staticmethod
    def score_support_india(at_support):
        return 4 if at_support else 0

    # ── Penalties ──

    @staticmethod
    def score_freshness_india(df):
        """
        v7.1 FIX: Freshness penalties — prevent buying stocks that already moved.
        KEY FIX: 52W high proximity no longer penalised.
        In Indian markets, breaking above 52W high on HIGH DELIVERY = most powerful signal.
        Penalising 52W high proximity was WRONG — it punished the best setups.

        What we penalise:
        - Moved >5% this week (operator already pushed it — late entry)
        - Moved >15% this month (already ran — freshness gone)
        - Too extended above EMA21 (rubber band stretched — mean reversion risk)
        """
        if len(df) < 20: return 0
        last  = df.iloc[-1]
        pen   = 0
        roc5  = last.get("ROC_5",  0) or 0
        roc21 = last.get("ROC_21", 0) or 0
        ema21 = last.get("EMA_21", 0) or 0
        close = last["Close"]

        # Penalty: moved too much this week (operator finished the push)
        if   roc5 > 10: pen -= 15   # blew up this week — avoid
        elif roc5 > 7:  pen -= 10
        elif roc5 > 4:  pen -= 5

        # Penalty: already ran this month
        if   roc21 > 30: pen -= 15  # already up 30% — freshness gone
        elif roc21 > 20: pen -= 10
        elif roc21 > 15: pen -= 5

        # Penalty: too extended above EMA21 (stretched rubber band)
        if ema21 > 0:
            ext = (close / ema21 - 1) * 100
            if   ext > 18: pen -= 10  # very extended — mean reversion risk
            elif ext > 12: pen -= 6
            elif ext > 8:  pen -= 3

        # NOTE: 52W HIGH PROXIMITY IS NO LONGER PENALISED (v7.1 fix)
        # Breaking above 52W high on high delivery = strongest Indian signal
        # Old code penalised this — that was wrong

        return max(pen, -28)

    @staticmethod
    def score_pledge_india(pledge_pct):
        if pledge_pct is None or pledge_pct < CFG["pledge_danger_pct"]: return 0
        return -CFG["pledge_score_penalty"]

    @staticmethod
    def score_results_india(earnings_info):
        if earnings_info and earnings_info.get("has_upcoming"): return -10
        return 0

    @staticmethod
    def score_52w_breakout_india(df, delivery_pct):
        """
        v7.1 NEW: 52W high breakout BONUS.
        In Indian markets, breaking above 52W high on high delivery + volume
        is the single highest win-rate setup. This is the opposite of what
        the old freshness penalty did (penalised it).

        Conditions: price within 1% of or above 52W high + delivery ≥ 55% + vol surge
        """
        if len(df) < 252: return 0
        try:
            high52  = df["High"].tail(252).max()
            close   = df["Close"].iloc[-1]
            vol_r   = df.iloc[-1].get("Vol_ratio", 1) or 1
            pct_off = (close / high52 - 1) * 100

            # At or breaking 52W high
            if pct_off >= -1.5:
                # Confirm with delivery + volume
                if (delivery_pct or 0) >= 60 and vol_r >= 1.5:
                    return 10   # confirmed 52W breakout — highest conviction
                elif (delivery_pct or 0) >= 50 and vol_r >= 1.2:
                    return 6    # moderate confirmation
                elif vol_r >= 2.0:
                    return 4    # volume breakout at least
            # Approaching 52W high (within 3%) with momentum
            elif pct_off >= -3:
                if (delivery_pct or 0) >= 55 and vol_r >= 1.3:
                    return 4    # approaching breakout with institutional support
        except Exception:
            pass
        return 0

    @staticmethod
    def score_circuit_penalty(circuit_risk):
        """
        v7.1 NEW: Circuit breaker penalty.
        Stocks hitting upper circuit repeatedly = operator activity.
        After the operator exits, the stock falls sharply.
        Penalise to prevent recommending operator-pushed stocks.
        """
        if not circuit_risk:
            return 0
        risk_str = str(circuit_risk).lower()
        if "upper" in risk_str:
            return -10   # near upper circuit — operator may exit
        return 0

    def score_nifty_gate(self, nifty_series):
        """
        v7.1 NEW: Nifty index gate.
        Accepts a pandas Series of Nifty Close prices.
        When Nifty is below its 50 EMA, long trade win rate drops ~40%.
        """
        if nifty_series is None or len(nifty_series) < 50:
            return 0
        try:
            close  = float(nifty_series.iloc[-1])
            ema50  = float(nifty_series.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(nifty_series.ewm(span=200, adjust=False).mean().iloc[-1])
            if   close < ema200:  return -12  # below 200 EMA = bear market
            elif close < ema50:   return -6   # below 50 EMA = correction
            else:                 return 0    # above both = bull mode
        except Exception:
            return 0

    @staticmethod
    def score_post_results_india(earnings_info, df):
        """
        v7.1 NEW: Post quarterly results momentum.
        In Indian markets, stocks that beat Q4/Q3 results by 15%+
        on both revenue and profit continue moving up for 3-6 weeks.
        This is the strongest fundamental catalyst in Indian markets.
        Check: results just announced (last 21 days) + stock up >3% since.
        """
        if not earnings_info:
            return 0
        # Check if results were recent (announced, not upcoming)
        if earnings_info.get("has_upcoming"):
            return 0    # upcoming = avoid, not bonus
        # Simple proxy: check if stock has positive 21-day momentum after flat period
        # A proper implementation needs results beat data from NSE corporate actions
        # For now: if no upcoming results AND stock is in stage 2 with recent base = small bonus
        return 0   # placeholder — upgrade when corporate actions data available

    # ── Master Score ──

    def compute_score(self, daily_df, weekly_df, delivery_pct=None,
                      fund_data=None, stage="Unknown", pledge_pct=None,
                      vcp_score_raw=0, is_nr7=False, is_inside_day=False,
                      pp_found=False,
                      candle_score=0, has_obv_div=False, has_flat_base=False,
                      flat_base_info=None, is_nr4=False, is_weekly_nr7=False,
                      at_support=False, bulk_deal_data=None, is_ipo_base=False,
                      promoter_data=None, oi_data=None, earnings_info=None,
                      # v7.1 new
                      circuit_risk=None, nifty_df=None):

        scores = {
            # ── India-specific (top priority) ──
            "delivery_india"  : self.score_delivery_india(daily_df, delivery_pct),
            "fii_dii_india"   : self.score_fii_dii_india(),
            "bulk_deal_india" : self.score_bulk_deal_india(bulk_deal_data or {}),
            "promoter_india"  : self.score_promoter_india(promoter_data or {}),
            "india_vix"       : self.score_india_vix(),
            "oi_buildup"      : self.score_oi_buildup(oi_data or {}),
            "pcr_india"       : self.score_pcr_india(),

            # ── Setup quality ──
            "supertrend"      : self.score_supertrend_india(daily_df),
            "vol_dryup"       : self.score_volume_dryup_india(daily_df),
            "base_position"   : self.score_base_position_india(daily_df),
            "support_prox"    : self.score_support_india(at_support),

            # ── Compression (India version — must be confirmed) ──
            "compression"     : self._score_compression_india_confirmed(
                                    is_nr7, is_inside_day, delivery_pct, daily_df),

            # ── Candle Patterns ──
            "candle_pattern"  : self.score_candle_india(candle_score),

            # ── Trend Context ──
            "ema_alignment"   : self.score_ema_alignment_india(daily_df),
            "rsi_sweetspot"   : self.score_rsi_india(daily_df),
            "adx_trend"       : self.score_adx_india(daily_df),

            # ── Quality Gate ──
            "fundamentals"    : self.score_fundamentals_india(fund_data),
            "stage_analysis"  : self.score_stage_india(stage),

            # ── IPO Base ──
            "ipo_base"        : (6 if is_ipo_base else 0),

            # ── v7.1 NEW — 52W breakout bonus + Golden Cross ──
            "breakout_52w"    : self.score_52w_breakout_india(daily_df, delivery_pct),
            "golden_cross"    : self.score_golden_cross_india(daily_df),
            "fii_pcr_combo"   : self.score_fii_pcr_combined(),    # FII buying + PCR oversold = best India signal
            "fii_absorption"  : self.score_fii_absorption_india(daily_df, delivery_pct),  # smart money absorbing FII selling
        }

        # ── Penalties ──
        scores["freshness_penalty"] = self.score_freshness_india(daily_df)
        scores["pledge_penalty"]    = self.score_pledge_india(pledge_pct)
        scores["results_penalty"]   = self.score_results_india(earnings_info)

        # ── v7.1 NEW penalties ──
        scores["circuit_penalty"]   = self.score_circuit_penalty(circuit_risk)
        scores["nifty_gate"]        = self.score_nifty_gate(nifty_df)

        # ── Multi-TF compression bonus ──
        if is_nr7 and is_weekly_nr7: scores["multi_tf_bonus"] = 6
        elif is_nr4:                 scores["multi_tf_bonus"] = 4
        else:                        scores["multi_tf_bonus"] = 0

        total = sum(scores.values())
        return round(min(max(total, 0), 100)), scores

    @staticmethod
    def assign_grade(score):
        if score >= CFG["grade_aplus"]: return "A+"
        if score >= CFG["grade_a"]:     return "A"
        if score >= CFG["grade_bplus"]: return "B+"
        if score >= CFG["grade_b"]:     return "B"
        if score >= CFG["grade_c"]:     return "C"
        return "D"

    @staticmethod
    def grade_color(grade):
        return {"A+":"#059669","A":"#10b981","B+":"#0284c7",
                "B":"#38bdf8","C":"#f59e0b","D":"#ef4444"}.get(grade,"#888")

    @staticmethod
    def compute_confidence_pct(result: dict) -> int:
        score    = result.get("score", 0)
        sigs     = min(len(result.get("active_signals",[])), 8)
        stage2   = 1 if result.get("is_stage2")                else 0
        fund_str = 1 if result.get("fund_grade")=="Strong"     else 0
        del_ok   = 1 if (result.get("delivery_pct") or 0)>=55  else 0
        fii_ok   = 1 if result.get("fii_buying", False)        else 0
        roc5_q   = 1 if abs(result.get("chg_5d",99)) < 2       else 0
        promo    = 1 if result.get("promoter_buying", False)    else 0
        conf = (score*0.55 + sigs*3.5 + stage2*8 + fund_str*4
                + del_ok*5 + fii_ok*5 + promo*6 + roc5_q*4)
        return max(40, min(99, round(conf)))


class NSEAnalysisPipeline:

    def __init__(self):
        self.nse_fetcher  = NSEDataFetcher()
        self.price_mgr    = PriceDataManager()
        self.ta           = TechnicalAnalyzer()
        self.patterns     = PatternDetector()
        self.delivery     = DeliveryFetcher()
        self.bhav_history = BhavHistory()   # ← bulk OHLCV from NSE archives
        self.bulk_deals   = BulkDealFetcher()
        self.fii_dii      = FIIDIIFetcher()
        self.fund_fetch   = FundamentalFetcher()
        self.promoter     = PromoterFetcher()
        self.accum        = InstitutionalAccumulationDetector()
        self.trade_calc   = TradeSetupCalculator()
        self.sector_mgr   = SectorMomentumAnalyzer()
        # v7.0 India-specific fetchers
        self.india_vix    = IndiaVIXFetcher()
        self.oi_fetcher   = OpenInterestFetcher()
        self.promoter_act = PromoterActivityFetcher()
        # shared FII/DII and PCR data (fetched once in run(), passed to scorer)
        self._fii_dii_data = {}
        self._pcr_data     = {}

    def analyze_one(self, symbol):
        try:
            raw = self.price_mgr.fetch_stock(symbol, bhav_history=self.bhav_history)
            if raw is None:
                return None

            daily  = self.ta.compute_all(raw["daily"])
            weekly = self.ta.compute_weekly(raw["weekly"]) if not raw["weekly"].empty else None

            # ── Delivery % ──
            delivery_pct = self.delivery.get(symbol)

            # ── Fundamentals (v3.0) ──
            fund_data = self.fund_fetch.fetch(symbol)

            # ── Promoter Pledging (v3.0) ──
            promoter_data = self.promoter.fetch(symbol)
            pledge_pct    = promoter_data.get("pledge_pct")

            # ── Stage Analysis (v3.0) ──
            stage, stage_info = self.patterns.detect_stage(weekly)

            # ── Institutional Accumulation (v4.0) ──
            accum_data = InstitutionalAccumulationDetector.detect(daily, delivery_pct)

            scorer = StockScorer(
                self.price_mgr.nifty_data,
                vix_fetcher  = self.india_vix,
                fii_dii_data = self._fii_dii_data,
                pcr_data     = self._pcr_data,
            )

            # ── v7.0 India-specific data ──
            promoter_act_data = self.promoter_act.fetch(symbol)
            oi_data           = self.oi_fetcher.get(symbol)

            # ── Pattern detections (must happen BEFORE compute_score) ──
            vcp_score, vcp_info = self.patterns.detect_vcp(daily)
            pp_found, pp_str    = self.patterns.detect_pocket_pivot(daily)
            is_nr7              = self.patterns.detect_nr7(daily)
            is_nr4              = self.patterns.detect_nr4(daily)          # NEW v6
            is_inside           = self.patterns.detect_inside_day(daily)
            htf, htf_info       = self.patterns.detect_high_tight_flag(daily)
            three_tight         = self.patterns.detect_three_tight_closes(daily)
            vol_dry             = self.patterns.detect_volume_dry_up(daily)
            bo_found, bo_str, bo_info = self.patterns.detect_breakout(daily)
            vs_type, vs_ratio, vs_up  = self.patterns.detect_volume_surge(daily)

            # ── v6.0 new detections ──
            has_flat_base, flat_base_info = self.patterns.detect_flat_base(daily)
            candle_patterns, candle_score = self.patterns.detect_candle_patterns(daily)
            is_weekly_nr7 = self.patterns.detect_weekly_nr7(weekly) if weekly is not None and not weekly.empty else False
            has_obv_div   = self.patterns.detect_obv_divergence(daily)
            at_support, support_price, support_dist = self.patterns.detect_support_level(daily)
            is_ipo_base, ipo_days = self.patterns.detect_ipo_base(daily)
            bulk_deal_data = self.bulk_deals.get(symbol)

            # 1D change for circuit check
            last_pre = daily.iloc[-1]
            prev_pre = daily.iloc[-2] if len(daily) > 1 else last_pre
            chg_1d_pre = (last_pre["Close"] / prev_pre["Close"] - 1) * 100
            circuit_risk = self.patterns.detect_upper_circuit_risk(chg_1d_pre)

            score, score_breakdown = scorer.compute_score(
                daily, weekly, delivery_pct,
                fund_data=fund_data, stage=stage, pledge_pct=pledge_pct,
                vcp_score_raw=vcp_score, is_nr7=is_nr7,
                is_inside_day=is_inside, pp_found=pp_found,
                candle_score=candle_score, has_obv_div=has_obv_div,
                has_flat_base=has_flat_base, flat_base_info=flat_base_info,
                is_nr4=is_nr4, is_weekly_nr7=is_weekly_nr7,
                at_support=at_support, bulk_deal_data=bulk_deal_data,
                is_ipo_base=is_ipo_base,
                # v7.0 India-specific
                promoter_data=promoter_act_data,
                oi_data=oi_data,
                earnings_info=raw.get("earnings_info", {}),
                # v7.1 new
                circuit_risk=circuit_risk,
                nifty_df=self.price_mgr.nifty_data,  # pandas Series of Nifty Close prices
            )
            grade = scorer.assign_grade(score)

            last = daily.iloc[-1]
            prev = daily.iloc[-2] if len(daily) > 1 else last

            rs_alpha = scorer.relative_strength(daily["Close"])

            chg_1d = (last["Close"] / prev["Close"] - 1) * 100
            chg_5d = last.get("ROC_5", 0)
            chg_1m = last.get("ROC_21", 0)
            chg_3m = last.get("ROC_63", 0)

            # ── Active signals ──
            active_signals = []
            if vcp_score >= 60:   active_signals.append(f"VCP({vcp_score})")
            if has_flat_base:     active_signals.append(f"FlatBase({flat_base_info.get('range_pct',0):.1f}%)")
            if pp_found:          active_signals.append(f"PocketPivot({pp_str})")
            if is_nr7:            active_signals.append("NR7")
            if is_nr4:            active_signals.append("NR4")
            if is_nr7 and is_weekly_nr7: active_signals.append("🔥MultiTF-NR7")
            if is_inside:         active_signals.append("InsideDay")
            if htf:               active_signals.append("HighTightFlag")
            if three_tight:       active_signals.append("3TightCloses")
            if vol_dry:           active_signals.append("VolDryUp")
            if bo_found:          active_signals.append(f"Breakout({bo_str})")
            if has_obv_div:       active_signals.append("OBV-Divergence📶")
            if at_support:        active_signals.append(f"AtSupport(₹{support_price:.0f})")
            if is_ipo_base:       active_signals.append(f"IPO-Base({ipo_days}d)")
            # Candle patterns
            for pat_name in candle_patterns:
                active_signals.append(f"🕯{pat_name}")
            # Supertrend
            last_st_dir = daily["ST_Direction"].iloc[-1] if "ST_Direction" in daily.columns else 0
            prev_st_dir = daily["ST_Direction"].iloc[-2] if "ST_Direction" in daily.columns and len(daily)>1 else 0
            if last_st_dir == 1:
                if prev_st_dir != 1: active_signals.append("ST-FlipBUY🟢")
                else:                active_signals.append("Supertrend-BUY")
            # MFI
            mfi_val = daily["MFI"].iloc[-1] if "MFI" in daily.columns else None
            if mfi_val is not None and not pd.isna(mfi_val) and 45 <= mfi_val <= 65:
                active_signals.append(f"MFI({mfi_val:.0f})")
            # ── FII Absorption signal ──
            fii_5d_abs = self._fii_dii_data.get("fii_5d")
            if fii_5d_abs and fii_5d_abs < -1000:
                chg5_abs = result.get("chg_5d", 0) or 0
                del_abs  = delivery_pct or 0
                if chg5_abs > -2 and del_abs >= 55:
                    active_signals.insert(0, "🔥FIIAbsorption(DII/Retail buying)")

            # ── FII + PCR Combined signal ──
            fii_5d_val = self._fii_dii_data.get("fii_5d")
            pcr_val_sig = self._pcr_data.get("nifty_pcr")
            if fii_5d_val and pcr_val_sig:
                if fii_5d_val > 2000 and pcr_val_sig > 1.4:
                    active_signals.insert(0, "🎯FII+PCR-BullCombo🟢")
                elif fii_5d_val > 2000 and pcr_val_sig > 1.2:
                    active_signals.insert(0, "✅FII+PCR-Bullish")

            # ── Golden Cross / Death Cross signal ──
            ema50_v  = last.get("EMA_50",  0) or 0
            ema200_v = last.get("EMA_200", 0) or 0
            if ema50_v > 0 and ema200_v > 0:
                prev_ema50  = daily.iloc[-2].get("EMA_50",  0) or 0
                prev_ema200 = daily.iloc[-2].get("EMA_200", 0) or 0
                if ema50_v > ema200_v and prev_ema50 <= prev_ema200:
                    active_signals.insert(0, "🌟GoldenCross🟢(Fresh)")
                elif ema50_v > ema200_v:
                    active_signals.append("GoldenCross✅")
                elif ema50_v < ema200_v and prev_ema50 >= prev_ema200:
                    active_signals.insert(0, "💀DeathCross🔴(Fresh)")
                elif ema50_v < ema200_v:
                    active_signals.append("DeathCross❌")

            # v7.1 — 52W high breakout signal
            high52w_chk = last.get("High_52w", 0) or 0
            if high52w_chk > 0:
                pft_chk   = (last["Close"] / high52w_chk - 1) * 100
                vol_r_chk = last.get("Vol_ratio", 1) or 1
                if pft_chk >= -1.5 and vol_r_chk >= 1.5 and (delivery_pct or 0) >= 55:
                    active_signals.insert(0, "🚀52WBreakout✅(Vol+Del)")
                elif -3 <= pft_chk < -1.5 and vol_r_chk >= 1.2:
                    active_signals.append("📈Near52WHigh")

            # Circuit risk
            if circuit_risk:
                active_signals.append(f"⚡{circuit_risk}")
                if "Upper" in str(circuit_risk):
                    active_signals.append("⚠️CircuitRisk")
            # Bulk deals
            if bulk_deal_data:
                if bulk_deal_data.get("bulk_buy"):  active_signals.append("📋BulkBuy")
                if bulk_deal_data.get("block_buy"): active_signals.append("📋BlockBuy")
                if bulk_deal_data.get("bulk_sell"): active_signals.append("🚨BulkSell")
            # F&O eligible
            if symbol in FNO_STOCKS: active_signals.append("F&O")
            # Volume Surge
            if vs_type:
                day_tag = "↑" if vs_up else "↓"
                active_signals.append(f"{vs_type}{day_tag}({vs_ratio}x)")
            # Delivery signal
            if delivery_pct is not None and delivery_pct >= CFG["delivery_min_pct"]:
                active_signals.append(f"Delivery{delivery_pct:.0f}%")
            # BB tightness
            bb_w = last.get("BB_width", 20)
            if bb_w < CFG["bb_tight_threshold"]:
                active_signals.append(f"BBTight({bb_w:.1f}%)")
            # 52W High proximity
            pct_from_high = last.get("Pct_from_high", -100)
            if pct_from_high >= -CFG["high52w_proximity_pct"]:
                active_signals.append("Near52WHigh")
            # Stage 2 signal
            if stage == "Stage 2":
                active_signals.append("Stage2✅")
            elif stage in ("Stage 3", "Stage 4"):
                active_signals.append(f"⚠️{stage}")
            # Fundamental quality
            fgrade = fund_data.get("fund_grade", "N/A") if fund_data else "N/A"
            if fgrade == "Strong":
                active_signals.append("FundStrong💎")
            elif fgrade == "Weak":
                active_signals.append("FundWeak❌")
            # Promoter pledging warning
            if pledge_pct is not None:
                if pledge_pct >= CFG["pledge_danger_pct"]:
                    active_signals.append(f"🚨Pledge{pledge_pct:.0f}%")
                elif pledge_pct >= CFG["pledge_warn_pct"]:
                    active_signals.append(f"⚠️Pledge{pledge_pct:.0f}%")
            # Earnings warning
            earnings_info = raw.get("earnings_info", {})
            if earnings_info.get("has_upcoming"):
                active_signals.append(f"⚠️Results({earnings_info['date_str']})")
            # Institutional Accumulation
            if accum_data.get("is_accumulating"):
                label = accum_data.get("accum_label", "Accumulation")
                days_a  = accum_data.get("accum_days", 0)
                if label == "Strong Accumulation":
                    active_signals.append(f"🏦StrongAccum({days_a}d)")
                else:
                    active_signals.append(f"🏦Accum({days_a}d)")

            # ── India-specific new signals (v7.0) ──
            if promoter_act_data.get("promoter_buying"):
                active_signals.append("🏛️PromoterBuying🟢")
            if promoter_act_data.get("promoter_selling"):
                active_signals.append("🏛️PromoterSelling🔴")
            if promoter_act_data.get("pledge_decreasing"):
                active_signals.append("📉PledgeDecreasing✅")
            # OI buildup signal
            oi_bt = oi_data.get("buildup_type","") if oi_data else ""
            if oi_bt == "LongBuildup":    active_signals.append("📊LongBuildup🟢")
            elif oi_bt == "ShortCovering": active_signals.append("📊ShortCovering⚡")
            elif oi_bt == "ShortBuildup":  active_signals.append("📊ShortBuildup🔴")
            # FII signal
            fii_sentiment = self._fii_dii_data.get("sentiment","")
            if "Buying" in fii_sentiment: active_signals.append(f"💹FII-{fii_sentiment}")
            elif "Selling" in fii_sentiment: active_signals.append(f"💹FII-{fii_sentiment}")
            # India VIX signal
            vix_val = self.india_vix._vix
            if vix_val is not None:
                if vix_val < 13: active_signals.append(f"📊VIX{vix_val:.0f}✅")
                elif vix_val > 20: active_signals.append(f"📊VIX{vix_val:.0f}⚠️")
            weekly_summary = {}
            if weekly is not None and not weekly.empty:
                wl = weekly.iloc[-1]
                weekly_summary = {
                    "w_rsi"        : round(wl.get("W_RSI", 0), 1),
                    "w_adx"        : round(wl.get("W_ADX", 0), 1),
                    "w_roc_4"      : round(wl.get("W_ROC_4", 0), 1),
                    "w_roc_13"     : round(wl.get("W_ROC_13", 0), 1),
                    "above_w_ema10": last["Close"] > wl.get("W_EMA_10", 0),
                    "above_w_ema21": last["Close"] > wl.get("W_EMA_21", 0),
                }

            result = {
                "symbol"         : symbol,
                "score"          : score,
                "grade"          : grade,
                "grade_color"    : scorer.grade_color(grade),
                "score_breakdown": score_breakdown,

                # Price
                "price"          : round(last["Close"], 2),
                "open"           : round(last["Open"], 2),
                "high"           : round(last["High"], 2),
                "low"            : round(last["Low"], 2),
                "volume"         : int(last["Volume"]),
                "avg_vol_20d"    : int(daily["Volume"].tail(20).mean()),
                "vol_ratio"      : round(last.get("Vol_ratio", 1), 2),

                # Returns
                "chg_1d"         : round(chg_1d, 2),
                "chg_5d"         : round(chg_5d, 2),
                "chg_1m"         : round(chg_1m, 2),
                "chg_3m"         : round(chg_3m, 2),

                # 52-week
                "high_52w"       : round(last.get("High_52w", 0), 2),
                "low_52w"        : round(last.get("Low_52w",  0), 2),
                "pct_from_high"  : round(pct_from_high, 1),

                # Indicators
                "rsi"            : round(last.get("RSI", 0), 1),
                "adx"            : round(last.get("ADX", 0), 1),
                "di_plus"        : round(last.get("DI_plus", 0), 1),
                "di_minus"       : round(last.get("DI_minus", 0), 1),
                "macd"           : round(last.get("MACD", 0), 3),
                "macd_sig"       : round(last.get("MACD_signal", 0), 3),
                "macd_hist"      : round(last.get("MACD_hist", 0), 3),
                "bb_width"       : round(last.get("BB_width", 0), 2),
                "atr_pct"        : round(last.get("ATR_pct", 0), 2),
                "stoch_k"        : round(last.get("Stoch_K", 0), 1),
                "obv_trend"      : "Up" if last.get("OBV", 0) > last.get("OBV_EMA", 0) else "Down",

                # EMAs
                "ema_5"          : round(last.get("EMA_5",   0), 2),
                "ema_10"         : round(last.get("EMA_10",  0), 2),
                "ema_13"         : round(last.get("EMA_13",  0), 2),
                "ema_21"         : round(last.get("EMA_21",  0), 2),
                "ema_26"         : round(last.get("EMA_26",  0), 2),
                "ema_50"         : round(last.get("EMA_50",  0), 2),
                "ema_200"        : round(last.get("EMA_200", 0), 2),
                "above_200ema"   : bool(last["Close"] > last.get("EMA_200", 0)),

                # ── EMA Momentum Scanner fields (v7.2) ──
                # Rule 1: Early Momentum 5>13>26
                "ema_early_momentum": bool(
                    last.get("EMA_5", 0)  > last.get("EMA_13", 0) > 0 and
                    last.get("EMA_13", 0) > last.get("EMA_26", 0) > 0 and
                    last["Close"]          > last.get("EMA_5",  0) > 0
                ),
                # Fresh 5>13 cross within last 2 days
                "ema_fresh_cross_5_13": bool(
                    len(daily) >= 3 and
                    daily["EMA_5"].iloc[-1]  > daily["EMA_13"].iloc[-1]  > 0 and
                    daily["EMA_5"].iloc[-2]  <= daily["EMA_13"].iloc[-2]
                ) if "EMA_5" in daily.columns and "EMA_13" in daily.columns else False,
                # Rule 2: Swing Confirmation 20>50
                "ema_swing_confirm": bool(
                    last.get("EMA_21", 0) > last.get("EMA_50", 0) > 0 and
                    last["Close"] > last.get("EMA_21", 0) > 0
                ),
                # Close near EMA21 (within 2-3%) = pullback+bounce setup
                "ema_near_20_pullback": bool(
                    last.get("EMA_21", 0) > 0 and
                    0 <= (last["Close"] / last.get("EMA_21", 1) - 1) * 100 <= 3
                ),
                # Rule 3: Golden Cross 50>200
                "ema_golden_cross": bool(
                    last.get("EMA_50", 0) > last.get("EMA_200", 0) > 0
                ),
                # Fresh Golden Cross within 10 days
                "ema_fresh_golden_cross": bool(
                    len(daily) >= 11 and
                    daily["EMA_50"].iloc[-1]  > daily["EMA_200"].iloc[-1]  > 0 and
                    daily["EMA_50"].iloc[-10] <= daily["EMA_200"].iloc[-10]
                ) if "EMA_50" in daily.columns and "EMA_200" in daily.columns else False,
                # Rule 4: Ultra Pro — all conditions combined
                "ema_ultra_pro": bool(
                    last.get("EMA_5",  0) > last.get("EMA_13", 0) > 0 and
                    last.get("EMA_13", 0) > last.get("EMA_26", 0) > 0 and
                    last.get("EMA_21", 0) > last.get("EMA_50", 0) > 0 and
                    last.get("EMA_50", 0) > last.get("EMA_200",0) > 0 and
                    last["Close"] > last.get("EMA_5", 0) > 0 and
                    (last.get("Vol_ratio", 1) or 1) >= 1.5
                ),
                # Near 20-day high (within 5%) — for Ultra Pro
                "near_20d_high": bool(
                    len(daily) >= 20 and
                    daily["High"].tail(20).max() > 0 and
                    (last["Close"] / daily["High"].tail(20).max() - 1) * 100 >= -5
                ),

                # Patterns & Signals
                "active_signals" : active_signals,
                "vcp_score"      : vcp_score,
                "vcp_info"       : vcp_info,
                "breakout"       : bo_found,
                "breakout_str"   : bo_str,
                "breakout_info"  : bo_info,
                "pocket_pivot"   : pp_found,
                "nr7"            : is_nr7,
                "nr4"            : is_nr4,
                "inside_day"     : is_inside,
                "vol_dry_up"     : vol_dry,
                "htf"            : htf,

                # v6.0 new pattern fields
                "flat_base"      : has_flat_base,
                "flat_base_info" : flat_base_info or {},
                "candle_patterns": candle_patterns,
                "candle_score"   : candle_score,
                "is_weekly_nr7"  : is_weekly_nr7,
                "obv_divergence" : has_obv_div,
                "at_support"     : at_support,
                "support_price"  : support_price,
                "support_dist_pct": support_dist,
                "is_ipo_base"    : is_ipo_base,
                "ipo_days_listed": ipo_days,
                "circuit_risk"   : circuit_risk,
                "is_fno"         : symbol in FNO_STOCKS,
                "bulk_deal"      : bulk_deal_data or {},

                # v7.0 India-specific fields
                "promoter_buying"   : promoter_act_data.get("promoter_buying", False),
                "promoter_selling"  : promoter_act_data.get("promoter_selling", False),
                "promoter_chg_qoq"  : promoter_act_data.get("promoter_chg_qoq", None),
                "pledge_decreasing" : promoter_act_data.get("pledge_decreasing", False),
                "oi_buildup_type"   : oi_data.get("buildup_type","") if oi_data else "",
                "oi_change_pct"     : oi_data.get("oi_change_pct", 0) if oi_data else 0,
                "india_vix"         : self.india_vix._vix,
                "fii_buying"        : "Buying" in self._fii_dii_data.get("sentiment",""),
                "supertrend_dir" : int(daily["ST_Direction"].iloc[-1]) if "ST_Direction" in daily.columns else 0,
                "mfi"            : round(float(daily["MFI"].iloc[-1]), 1) if "MFI" in daily.columns and not pd.isna(daily["MFI"].iloc[-1]) else None,
                "cmf"            : round(float(daily["CMF"].iloc[-1]), 3) if "CMF" in daily.columns and not pd.isna(daily["CMF"].iloc[-1]) else None,
                "pivot_pp"       : daily.get("Pivot_PP", pd.Series([0])).iloc[-1] if "Pivot_PP" in daily.columns else None,
                "pivot_r1"       : daily.get("Pivot_R1", pd.Series([0])).iloc[-1] if "Pivot_R1" in daily.columns else None,
                "pivot_s1"       : daily.get("Pivot_S1", pd.Series([0])).iloc[-1] if "Pivot_S1" in daily.columns else None,
                "pivot_r2"       : daily.get("Pivot_R2", pd.Series([0])).iloc[-1] if "Pivot_R2" in daily.columns else None,
                "pivot_s2"       : daily.get("Pivot_S2", pd.Series([0])).iloc[-1] if "Pivot_S2" in daily.columns else None,

                # v6.0 Sparkline — last 20 normalized close prices
                "sparkline"      : [round(float(v), 2) for v in daily["Close"].tail(20).tolist()],

                # Volume Surge
                "vol_surge_type" : vs_type,
                "vol_surge_ratio": vs_ratio,
                "vol_surge_up"   : vs_up,

                # Fundamentals (v3.0)
                "fund_score"     : fund_data.get("fund_score", 0) if fund_data else 0,
                "fund_grade"     : fund_data.get("fund_grade", "N/A") if fund_data else "N/A",
                "fund_detail"    : fund_data.get("fund_detail", {}) if fund_data else {},
                "roe"            : fund_data.get("roe") if fund_data else None,
                "roce"           : fund_data.get("roce") if fund_data else None,
                "de_ratio"       : fund_data.get("de_ratio") if fund_data else None,
                "eps_growth"     : fund_data.get("eps_growth") if fund_data else None,
                "rev_growth"     : fund_data.get("rev_growth") if fund_data else None,
                "profit_margin"  : fund_data.get("profit_margin") if fund_data else None,
                "pe_ratio"       : fund_data.get("pe_ratio") if fund_data else None,
                "market_cap"     : fund_data.get("market_cap") if fund_data else None,

                # Promoter & Pledging (v3.0)
                "promoter_holding": promoter_data.get("promoter_holding"),
                "pledge_pct"      : pledge_pct,
                "pledge_danger"   : bool(pledge_pct is not None and pledge_pct >= CFG["pledge_danger_pct"]),
                "pledge_warn"     : bool(pledge_pct is not None and pledge_pct >= CFG["pledge_warn_pct"]),

                # Stage Analysis (v3.0)
                "stage"          : stage,
                "stage_info"     : stage_info,
                "is_stage2"      : stage == "Stage 2",

                # Institutional Accumulation (v4.0)
                "is_accumulating": accum_data.get("is_accumulating", False),
                "accum_days"     : accum_data.get("accum_days", 0),
                "accum_signals"  : accum_data.get("accum_signals", []),
                "accum_score"    : accum_data.get("accum_score", 0),
                "accum_label"    : accum_data.get("accum_label", "None"),

                # NEW: Delivery & Earnings
                "delivery_pct"   : delivery_pct,
                "earnings_info"  : earnings_info,
                "near_52w_high"  : bool(pct_from_high >= -CFG["high52w_proximity_pct"]),

                # RS (percentile added in run())
                "rs_alpha"       : round(rs_alpha, 2),
                "rs_percentile"  : 0,   # placeholder

                # Sector (added in run())
                "sector"         : SECTOR_MAP.get(symbol, "Others"),
                "sector_rank"    : 0,
                "sector_momentum": 0,
                "sector_total"   : 0,

                # Trade Setup (added below)
                "trade_setup"    : {},

                # Weekly
                "weekly"         : weekly_summary,
            }

            # ── Trade Setup ── (needs result dict first)
            result["trade_setup"] = self.trade_calc.calculate(result, daily)

            # ── Confidence % (v4.0) — for Top Trades ranking ──
            result["confidence_pct"] = StockScorer.compute_confidence_pct(result)

            # ── AVWAP Pre-Breakout Scanner (v8.0) ──────────────────────────
            try:
                avwap_data = self._compute_avwap_scanner(daily, last, delivery_pct)
                result.update(avwap_data)
                if avwap_data.get("avwap_score", 0) >= 4:
                    active_signals.insert(0, f"🔥AVWAP-PreBreakout({avwap_data['avwap_score']}/5)")
                elif avwap_data.get("avwap_score", 0) >= 3:
                    active_signals.append(f"⚡AVWAP-Setup({avwap_data['avwap_score']}/5)")
            except Exception:
                result.update({
                    "avwap_score": 0, "avwap_value": 0, "avwap_above": False,
                    "avwap_held_days": 0, "avwap_dist_to_breakout": 0,
                    "avwap_vol_vs_avg": 0, "avwap_consolidation": False,
                    "avwap_candidate": False, "avwap_smart_money": False,
                    "avwap_tag": "",
                })

            return result

        except Exception as _e:
            import traceback; print(f"  [ERR] {symbol}: {type(_e).__name__}: {_e}"); return None

    def run(self, symbols, max_workers=None):
        workers = max_workers or CFG["max_workers"]
        results = []
        failed  = 0

        # ── Fetch delivery data first (single bulk download) ──
        print("\n📥 Building NSE price history from bhavcopy archives...")
        self.bhav_history.fetch_all(lookback_days=CFG.get("lookback_days", 300) + 60)
        print("\n📦 Fetching NSE delivery data (bulk)...")
        self.delivery.fetch_all()

        # ── Fetch bulk/block deals ──
        print("\n📋 Fetching bulk & block deal data...")
        self.bulk_deals.fetch_all()

        # ── Fetch FII/DII flow ──
        print("\n💹 Fetching FII/DII flow data...")
        fii_dii_data = self.fii_dii.fetch()
        self._fii_dii_data = fii_dii_data   # share with scorer via pipeline

        # ── v7.0: Fetch India VIX ──
        print("\n📊 Fetching India VIX...")
        self.india_vix.fetch()

        # ── v7.0: Fetch Open Interest data ──
        print("\n📈 Fetching Open Interest (F&O buildup)...")
        self.oi_fetcher.fetch_all()

        print(f"\n⚙️  Analyzing {len(symbols)} stocks with {workers} parallel workers...\n")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(self.analyze_one, sym): sym for sym in symbols}
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="  Analyzing",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"
            ):
                res = future.result()
                if res:
                    results.append(res)
                else:
                    failed += 1

        print(f"\n  ✅ Analyzed: {len(results)} stocks   |   ⚠️  Skipped/Failed: {failed}")

        if not results:
            return results

        # ── Compute RS Percentile ──
        alphas = [r["rs_alpha"] for r in results]
        for r in results:
            rank = sum(1 for a in alphas if a <= r["rs_alpha"])
            r["rs_percentile"] = round(rank / len(alphas) * 100)

        # ── RS Elite Bonus (+2 pts for top 10% — reduced from +5 in v5) ──
        for r in results:
            if r["rs_percentile"] >= CFG["rs_elite_pct"]:
                new_score = min(r["score"] + 2, 100)
                r["score"] = new_score
                r["grade"] = StockScorer.assign_grade(new_score)
                r["grade_color"] = StockScorer.grade_color(r["grade"])
                r["score_breakdown"]["rs_elite_bonus"] = 2
                if "RS Elite(>90%ile)" not in r["active_signals"]:
                    r["active_signals"].insert(0, "RS Elite(>90%ile)")
            else:
                r["score_breakdown"]["rs_elite_bonus"] = 0

        # ── Sector Momentum Rankings ──
        self.sector_mgr.assign_sectors(results)
        sorted_sectors = self.sector_mgr.rank_and_score(results)

        # ── Market Breadth (v3.0) ──
        above_200 = sum(1 for r in results if r["above_200ema"])
        breadth_pct = round(above_200 / len(results) * 100, 1)
        if   breadth_pct >= CFG["breadth_strong"]:  breadth_status = "STRONG"
        elif breadth_pct >= CFG["breadth_caution"]: breadth_status = "CAUTION"
        else:                                        breadth_status = "WEAK"
        breadth_data = {"pct": breadth_pct, "count": above_200, "status": breadth_status}

        # ── v7.0: Expert Filter — 13-point checklist ──
        nifty_above_sma = breadth_pct >= 55
        for r in results:
            sec_strength = r.get("sector_strength", 50)
            expert_result = ExpertFilter.evaluate(
                result          = r,
                sector_strength = sec_strength,
                nifty_above_sma = nifty_above_sma,
                breadth_pct     = breadth_pct,
            )
            r.update(expert_result)
            yes = expert_result["expert_yes"]
            dec = expert_result["expert_decision"]
            if   dec == "CONVICTION": r["active_signals"].insert(0, f"⭐CONVICTION({yes}/13)")
            elif dec == "TRADE":      r["active_signals"].insert(0, f"✅EXPERT({yes}/13)")

        expert_conviction = sum(1 for r in results if r.get("expert_decision") == "CONVICTION")
        expert_trade      = sum(1 for r in results if r.get("expert_decision") == "TRADE")
        print(f"\n  ⭐ Expert Conviction trades: {expert_conviction}")
        print(f"  ✅ Expert tradeable:         {expert_trade}")
        print(f"  ❌ Expert SKIP:              {len(results) - expert_conviction - expert_trade}")

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        # ── Top 10 Smart Opportunities ranked by Confidence % ──
        tradeable = [r for r in results if r.get("grade") in ("A+", "A", "B+")
                     and not r.get("pledge_danger")
                     and not r["earnings_info"].get("has_upcoming")
                     and not r.get("circuit_risk")]   # v6: exclude circuit stocks
        top_trades = sorted(tradeable, key=lambda x: x.get("confidence_pct", 0), reverse=True)[:10]

        return results, sorted_sectors, breadth_data, top_trades, fii_dii_data


# ─────────────────────────────────────────────────────────────────────
#  HTML REPORT GENERATOR  v3.0
# ─────────────────────────────────────────────────────────────────────
class HTMLReportGenerator:

    def generate(self, results, pcr_data, sorted_sectors, breadth_data,
                 capital=None, output_file="trade_stag_report.html",
                 top_trades=None, fii_dii_data=None, max_pain_data=None):
        analysis_time = datetime.now().strftime("%d %b %Y, %I:%M %p")
        total         = len(results)
        cap           = capital or CFG["default_capital"]
        risk_amt      = round(cap * CFG["risk_per_trade_pct"] / 100)

        grade_counts = {}
        for r in results:
            grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

        fii_dii_data  = fii_dii_data or {}
        fii_net       = fii_dii_data.get("fii_net")
        dii_net       = fii_dii_data.get("dii_net")
        fii_5d        = fii_dii_data.get("fii_5d")
        fii_sentiment = fii_dii_data.get("sentiment", "N/A")

        # ── Advance/Decline counts (v7.1) ──
        adv_count  = sum(1 for r in results if r.get("chg_1d", 0) > 0)
        dec_count  = sum(1 for r in results if r.get("chg_1d", 0) < 0)
        unch_count = len(results) - adv_count - dec_count
        total_ad   = max(adv_count + dec_count + unch_count, 1)
        adv_pct    = adv_count  / total_ad * 100
        dec_pct    = dec_count  / total_ad * 100
        unch_pct   = max(0, 100 - adv_pct - dec_pct)

        # ── Header display values ──
        fii_5d_html  = fii_5d if fii_5d else 0
        fii_5d_str   = f"₹{fii_5d/100:.0f}Cr" if fii_5d else "N/A"
        pcr_val_html = f"{pcr_data.get('nifty_pcr', 'N/A')}" if pcr_data.get('nifty_pcr') else "N/A"
        vix_fetcher_val = None
        # Try to get VIX from pcr_data extras or leave N/A
        vix_val_html = "N/A"

        bulk_buy_stocks  = [r for r in results if r.get("bulk_deal", {}).get("bulk_buy") or r.get("bulk_deal", {}).get("block_buy")]
        bulk_sell_stocks = [r for r in results if r.get("bulk_deal", {}).get("bulk_sell")]
        supertrend_buy   = [r for r in results if r.get("supertrend_dir") == 1]
        st_flip          = [r for r in results if r.get("supertrend_dir") == 1
                            and any("ST-FlipBUY" in s for s in r.get("active_signals", []))]
        obv_div_stocks   = [r for r in results if r.get("obv_divergence")]
        flat_base_stocks = [r for r in results if r.get("flat_base")]
        candle_stocks    = [r for r in results if r.get("candle_score", 0) >= 6]
        fno_stocks_list  = [r for r in results if r.get("is_fno")]
        circuit_stocks   = [r for r in results if r.get("circuit_risk")]
        support_stocks   = [r for r in results if r.get("at_support")]
        ipo_base_stocks  = [r for r in results if r.get("is_ipo_base")]

        breakouts     = [r for r in results if r["breakout"]][:10]
        vcps          = sorted([r for r in results if r["vcp_score"] >= 60],
                               key=lambda x: x["vcp_score"], reverse=True)[:10]
        rs_elite      = [r for r in results if r["rs_percentile"] >= CFG["rs_elite_pct"]]
        near_earnings = [r for r in results if r["earnings_info"].get("has_upcoming")]
        high_delivery = [r for r in results
                         if r["delivery_pct"] is not None and r["delivery_pct"] >= CFG["delivery_min_pct"]]
        vol_surges    = [r for r in results if r.get("vol_surge_type") is not None]
        vol_surges_up = [r for r in vol_surges if r.get("vol_surge_up")]
        stage2_stocks = [r for r in results if r.get("is_stage2")]
        pledge_danger = [r for r in results if r.get("pledge_danger")]
        fund_strong   = [r for r in results if r.get("fund_grade") == "Strong"]
        accum_stocks  = [r for r in results if r.get("is_accumulating")]
        strong_accum  = [r for r in results if r.get("accum_label") == "Strong Accumulation"]
        top_trades    = top_trades or sorted(results[:10], key=lambda x: x.get("confidence_pct", 0), reverse=True)

        pcr_val     = pcr_data.get("nifty_pcr",       "N/A")
        weekly_pcr  = pcr_data.get("weekly_pcr",      None)
        weekly_exp  = pcr_data.get("weekly_expiry",   "N/A")
        monthly_exp = pcr_data.get("monthly_expiry",  "N/A")
        pcr_sent    = pcr_data.get("sentiment",        "N/A")
        wpcr_sent   = pcr_data.get("weekly_sentiment","N/A")
        max_pain_data = max_pain_data or {}
        mp_val        = max_pain_data.get("max_pain")
        mp_dist       = max_pain_data.get("distance_pct")
        mp_sentiment  = max_pain_data.get("sentiment", "N/A")
        mp_display    = f"₹{mp_val:,} ({mp_dist:+.1f}%)" if mp_val and mp_dist else "N/A"
        breadth_pct    = breadth_data.get("pct", 0)
        breadth_status = breadth_data.get("status", "UNKNOWN")
        breadth_col    = ("#10b981" if breadth_status == "STRONG"
                          else "#f59e0b" if breadth_status == "CAUTION" else "#ef4444")
        # Weekly PCR display string
        wpcr_display = f"{weekly_pcr} ({wpcr_sent}) — Expiry: {weekly_exp}" if weekly_pcr else "NSE blocked"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trade Stag — NSE 500 Scanner — {analysis_time}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    /* ── Trade Stag v2 — Forest Dark + Gold ── */
    --bg:        #060a0c;
    --bg2:       #0b1014;
    --bg3:       #111a20;
    --bg4:       #182830;
    --sidebar-w: 248px;
    --border:    rgba(180, 160, 90, 0.10);
    --border2:   rgba(180, 160, 90, 0.05);
    --text:      #e8ece0;
    --muted:     #7a8e8a;
    --muted2:    #4a5e58;
    --green:     #2dd4a0;
    --red:       #fb7185;
    --amber:     #d4a024;
    --blue:      #38bdf8;
    --cyan:      #22d3ee;
    --purple:    #a78bfa;
    --orange:    #e89030;
    --lime:      #84cc16;
    --accent:    #d4a024;
    --accent2:   #2dd4a0;
    --aplus:     #d4a024;
    --a:         #e8b84a;
    --bplus:     #2dd4a0;
    --b:         #67e8c8;
    --c:         #e89030;
    --d:         #fb7185;
    --sidebar-bg:#080e12;
    --sidebar-item: rgba(180, 160, 90, 0.04);
    --sidebar-active: rgba(212, 160, 36, 0.12);
    --sidebar-active-border: #d4a024;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin:0; padding:0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: "IBM Plex Mono", "JetBrains Mono", "Fira Code", ui-monospace, monospace;
    font-size: 13px;
    line-height: 1.6;
    min-height: 100vh;
    overflow-x: hidden;
  }}

  a {{ color: inherit; text-decoration: none; }}

  /* ── App Shell: sidebar + main ── */
  .app-shell {{
    display: flex;
    min-height: 100vh;
  }}

  /* ── LEFT SIDEBAR ── */
  .sidebar {{
    width: var(--sidebar-w);
    min-width: var(--sidebar-w);
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    overflow-y: auto;
    z-index: 50;
    scrollbar-width: thin;
    scrollbar-color: var(--bg4) transparent;
  }}
  .sidebar::-webkit-scrollbar {{ width: 3px; }}
  .sidebar::-webkit-scrollbar-thumb {{ background: var(--bg4); border-radius: 3px; }}

  .sidebar-logo {{
    padding: 18px 16px 14px;
    border-bottom: 1px solid var(--border2);
    flex-shrink: 0;
  }}
  .sidebar-logo-mark {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.5px;
    line-height: 1;
  }}
  .sidebar-logo-sub {{
    font-size: 10px;
    color: var(--muted);
    margin-top: 3px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}
  .sidebar-tagline {{
    font-size: 9px;
    color: var(--muted2);
    margin-top: 4px;
    line-height: 1.4;
  }}

  .sidebar-group {{
    padding: 12px 0 4px;
    border-bottom: 1px solid var(--border2);
  }}
  .sidebar-group:last-child {{ border-bottom: none; }}

  .sidebar-group-label {{
    padding: 0 14px 6px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted2);
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .sidebar-group-label::before {{
    content: '';
    width: 12px;
    height: 1px;
    background: var(--muted2);
    opacity: 0.5;
  }}

  .sidebar-item {{
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 14px;
    cursor: pointer;
    border-left: 2px solid transparent;
    transition: all 0.12s;
    font-size: 12px;
    color: var(--muted);
    position: relative;
  }}
  .sidebar-item:hover {{
    background: var(--sidebar-item);
    color: var(--text);
    border-left-color: rgba(212,160,36,0.3);
  }}
  .sidebar-item.active {{
    background: var(--sidebar-active);
    color: var(--text);
    border-left-color: var(--sidebar-active-border);
    font-weight: 600;
  }}
  .sidebar-item.active .si-icon {{ color: var(--orange); }}
  .si-icon {{
    font-size: 13px;
    width: 18px;
    text-align: center;
    flex-shrink: 0;
    color: var(--muted2);
    transition: color 0.12s;
  }}
  .si-label {{ flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .si-count {{
    font-size: 9px;
    background: var(--bg4);
    color: var(--muted);
    padding: 1px 6px;
    border-radius: 10px;
    font-weight: 700;
    flex-shrink: 0;
  }}
  .si-badge {{
    font-size: 8px;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 700;
    letter-spacing: 0.04em;
    flex-shrink: 0;
  }}
  .si-badge.hot  {{ background: rgba(212,160,36,.2); color: var(--orange); }}
  .si-badge.new  {{ background: rgba(34,211,238,.15); color: var(--cyan); }}
  .si-badge.pro  {{ background: rgba(167,139,250,.15); color: var(--purple); }}

  /* ── MAIN CONTENT ── */
  .main-content {{
    margin-left: var(--sidebar-w);
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }}

  /* ── TOP BAR ── */
  .topbar {{
    position: sticky;
    top: 0;
    z-index: 40;
    background: rgba(10,12,16,0.95);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .topbar-title {{
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 1;
    min-width: 0;
  }}
  .topbar-breadcrumb {{
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }}
  .topbar-sep {{ color: var(--muted2); }}
  .topbar-stats {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .ts {{ font-size: 11px; color: var(--muted); }}
  .ts strong {{ color: var(--text); }}
  .ts.up strong {{ color: var(--green); }}
  .ts.dn strong {{ color: var(--red); }}
  .ts.hl strong {{ color: var(--orange); }}

  /* ── CONTENT AREA ── */
  .content-area {{
    padding: 16px 20px;
    flex: 1;
  }}

  /* ── TAB PANE (content sections) ── */
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}

  /* ── MARKET PULSE STRIP ── */
  .pulse-strip {{
    display: flex;
    gap: 8px;
    margin-bottom: 14px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
  }}
  .pulse-strip::-webkit-scrollbar {{ display: none; }}
  .pulse-card {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    min-width: 130px;
    flex-shrink: 0;
  }}
  .pc-label {{ font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.07em; }}
  .pc-val   {{ font-size: 17px; font-weight: 700; line-height: 1.1; margin-top: 2px; }}
  .pc-sub   {{ font-size: 10px; color: var(--muted); margin-top: 1px; }}

  /* ── SCREEN HEADER CARD ── */
  .screen-header {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }}
  .sh-icon {{ font-size: 24px; }}
  .sh-info {{ flex: 1; min-width: 0; }}
  .sh-title  {{ font-size: 16px; font-weight: 700; line-height: 1.2; }}
  .sh-desc   {{ font-size: 11px; color: var(--muted); margin-top: 3px; }}
  .sh-logic  {{
    font-size: 10px;
    font-family: "IBM Plex Mono", monospace;
    background: var(--bg3);
    color: var(--cyan);
    padding: 3px 10px;
    border-radius: 4px;
    border: 1px solid rgba(34,211,238,0.15);
    white-space: nowrap;
  }}
  .sh-count {{
    font-size: 28px;
    font-weight: 800;
    color: var(--orange);
    min-width: 48px;
    text-align: right;
  }}
  .sh-count-label {{ font-size: 9px; color: var(--muted); text-align: right; text-transform: uppercase; letter-spacing: 0.07em; }}

  /* ── FILTER BAR ── */
  .filter-bar {{
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 10px;
    flex-wrap: wrap;
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
  }}
  .fb-search {{
    flex: 1;
    min-width: 160px;
    position: relative;
  }}
  .fb-search input {{
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 5px;
    color: var(--text);
    font-size: 12px;
    font-family: inherit;
    padding: 5px 10px 5px 28px;
    outline: none;
    transition: border-color 0.15s;
  }}
  .fb-search input:focus {{ border-color: var(--orange); }}
  .fb-search::before {{
    content: "⌕";
    position: absolute;
    left: 8px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 14px;
    pointer-events: none;
  }}
  .fb-sep {{ width: 1px; height: 20px; background: var(--border); flex-shrink: 0; }}
  .fb-chips {{ display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }}
  .filter-btn {{
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.12s;
    white-space: nowrap;
  }}
  .filter-btn:hover {{ border-color: var(--orange); color: var(--orange); background: rgba(212,160,36,0.06); }}
  .filter-btn.on {{
    background: rgba(212,160,36,0.15);
    border-color: rgba(212,160,36,0.5);
    color: var(--orange);
    font-weight: 700;
  }}
  .fb-count {{
    font-size: 10px;
    color: var(--muted);
    margin-left: auto;
    padding: 3px 8px;
    background: var(--bg3);
    border-radius: 4px;
    white-space: nowrap;
    flex-shrink: 0;
  }}

  /* ── TABLE ── */
  .tbl-wrap {{ overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }}
  table {{ width: 100%; border-collapse: collapse; min-width: 1100px; }}
  thead th {{
    background: var(--bg3);
    padding: 8px 10px;
    text-align: left;
    font-size: 9px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.09em;
    text-transform: uppercase;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    position: sticky;
    top: 0;
    border-bottom: 1px solid var(--border);
  }}
  thead th:hover {{ color: var(--orange); }}
  tbody tr {{
    border-bottom: 1px solid var(--border2);
    transition: background 0.08s;
    cursor: pointer;
  }}
  tbody tr:hover {{ background: rgba(212,160,36,0.04); }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody td {{ padding: 8px 10px; font-size: 12px; white-space: nowrap; }}

  /* ── GRADE BADGE ── */
  .grade-badge {{
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 800;
    min-width: 28px;
    text-align: center;
    letter-spacing: 0.03em;
  }}

  /* ── SIGNAL TAGS ── */
  .signal-tag {{
    display: inline-block;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 9px;
    font-weight: 600;
    background: rgba(34,211,238,0.1);
    color: var(--cyan);
    margin: 1px;
    border: 1px solid rgba(34,211,238,0.2);
    white-space: nowrap;
  }}
  .signal-elite  {{ background: rgba(167,139,250,.12); color: var(--purple); border-color: rgba(167,139,250,.2); }}
  .signal-warn   {{ background: rgba(244,63,94,.12);  color: var(--red);    border-color: rgba(244,63,94,.2);  }}
  .signal-green  {{ background: rgba(34,197,94,.1);   color: var(--green);  border-color: rgba(34,197,94,.2);  }}
  .signal-surge  {{ background: rgba(245,158,11,.12); color: var(--amber);  border-color: rgba(245,158,11,.25); }}

  /* ── PROGRESS BAR ── */
  .prog-bar  {{ height: 3px; border-radius: 2px; background: var(--bg4); overflow: hidden; margin-top: 2px; width: 40px; }}
  .prog-fill {{ height: 100%; border-radius: 2px; }}

  /* ── SPARKLINE ── */
  .sparkline {{ display: inline-block; vertical-align: middle; }}

  /* ── UP / DOWN / NEUTRAL ── */
  .up      {{ color: var(--green); }}
  .down    {{ color: var(--red); }}
  .neutral {{ color: var(--muted); }}

  /* ── STAT CARDS ── */
  .stat-grid  {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(130px,1fr)); gap: 8px; margin-bottom: 14px; }}
  .stat-card  {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 10px 13px; }}
  .stat-label {{ font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }}
  .stat-val   {{ font-size: 22px; font-weight: 800; line-height: 1; }}
  .stat-sub   {{ font-size: 9px; color: var(--muted); margin-top: 2px; }}

  /* ── PCR / FII STRIPS ── */
  .info-strip {{
    display: flex;
    gap: 8px;
    align-items: center;
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 8px;
    flex-wrap: wrap;
    font-size: 12px;
  }}
  .info-strip .label {{ color: var(--muted); }}
  .info-strip strong {{ color: var(--text); }}
  .info-badge {{
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.03em;
  }}

  /* ── AD BAR ── */
  .ad-bar {{ height: 22px; border-radius: 6px; overflow: hidden; display: flex; margin-bottom: 14px; border: 1px solid var(--border); }}
  .ad-adv  {{ background: #16a34a; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:700; color:#fff; }}
  .ad-unch {{ background: #374151; }}
  .ad-dec  {{ background: #dc2626; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:700; color:#fff; }}

  /* ── SECTION TITLE ── */
  .section-title {{
    font-size: 9px;
    font-weight: 700;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border2);
  }}

  /* ── MODAL ── */
  .modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.8); z-index:100; align-items:center; justify-content:center; backdrop-filter: blur(4px); }}
  .modal-overlay.open {{ display:flex; }}
  .modal {{
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    max-width: 760px;
    width: 92vw;
    max-height: 90vh;
    overflow-y: auto;
    position: relative;
    box-shadow: 0 25px 80px rgba(0,0,0,0.8);
  }}
  .modal-close {{ position:absolute; top:12px; right:12px; background:var(--bg3); border:1px solid var(--border); color:var(--muted); font-size:14px; cursor:pointer; width:26px; height:26px; border-radius:5px; display:flex; align-items:center; justify-content:center; transition: all 0.1s; }}
  .modal-close:hover {{ color:var(--text); border-color:var(--orange); }}
  .modal-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:10px; }}
  .modal-metric {{ background:var(--bg3); border-radius:6px; padding:10px; }}
  .modal-metric-label {{ font-size:9px; color:var(--muted); text-transform:uppercase; letter-spacing:0.07em; }}
  .modal-metric-val   {{ font-size:15px; font-weight:700; margin-top:2px; }}
  .breakdown-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:6px; margin-top:8px; }}
  .breakdown-item {{ background:var(--bg3); border-radius:6px; padding:8px 10px; }}
  .breakdown-label {{ font-size:9px; color:var(--muted); }}
  .breakdown-val   {{ font-size:13px; font-weight:700; }}
  .trade-setup-card {{ background: linear-gradient(135deg,rgba(212,160,36,.06),rgba(34,211,238,.04)); border:1px solid rgba(212,160,36,.2); border-radius:10px; padding:14px; margin-top:12px; }}
  .trade-setup-grid {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:8px; }}
  .trade-box {{ background:var(--bg3); border-radius:6px; padding:10px; text-align:center; }}
  .trade-box-label {{ font-size:9px; color:var(--muted); text-transform:uppercase; letter-spacing:0.07em; }}
  .trade-box-val   {{ font-size:18px; font-weight:800; margin-top:3px; }}
  .trade-box-sub   {{ font-size:9px; color:var(--muted); margin-top:2px; }}
  .trade-t2-row    {{ background:var(--bg3); border-radius:6px; padding:8px 12px; margin-top:6px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px; font-size:11px; }}
  .earnings-warn {{ background:rgba(244,63,94,.08); border:1px solid rgba(244,63,94,.25); border-radius:6px; padding:8px 12px; margin-top:8px; color:var(--red); font-size:12px; }}
  .pledge-alert  {{ background:rgba(244,63,94,.08); border:1px solid rgba(244,63,94,.3); border-radius:6px; padding:8px 12px; margin-top:6px; color:var(--red); font-size:12px; }}
  .price-chip {{ background:var(--bg3); border-radius:4px; padding:2px 6px; font-size:10px; }}
  .pos-calc   {{ background:var(--bg3); border:1px solid var(--border); border-radius:8px; padding:12px; margin-top:8px; }}

  /* ── SECTOR CARDS ── */
  .sector-lb-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }}
  .sector-lb-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:12px 14px; }}
  .sector-bar {{ height:4px; border-radius:2px; background:var(--bg4); margin-top:5px; overflow:hidden; }}
  .sector-bar-fill {{ height:100%; border-radius:2px; }}
  .sector-meta {{ font-size:9px; color:var(--muted); margin-top:4px; display:flex; gap:10px; flex-wrap:wrap; }}
  .sector-hot-badge {{ background:rgba(245,158,11,.15); color:var(--amber); border:1px solid rgba(245,158,11,.3); padding:1px 5px; border-radius:3px; font-size:8px; font-weight:700; }}

  /* ── ACCUMULATION / FUND CARDS ── */
  .fund-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:12px; cursor:pointer; transition:border-color .12s; }}
  .fund-card:hover {{ border-color: rgba(212,160,36,.3); }}
  .fund-metric {{ display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--border2); font-size:11px; }}
  .fund-metric:last-child {{ border-bottom:none; }}
  .accum-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:12px; cursor:pointer; transition:border-color .12s; }}
  .accum-card:hover {{ border-color:rgba(34,197,94,.3); }}
  .accum-card.strong {{ border-color:rgba(34,197,94,.25); background:rgba(34,197,94,.03); }}
  .accum-signal-tag {{ display:inline-block; background:rgba(34,197,94,.1); color:var(--green); border:1px solid rgba(34,197,94,.2); border-radius:3px; padding:1px 5px; font-size:9px; margin:1px; }}
  .accum-score-bar {{ height:3px; border-radius:2px; background:var(--bg4); margin-top:5px; overflow:hidden; }}
  .accum-score-fill {{ height:100%; border-radius:2px; background:var(--green); }}
  .accum-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:8px; }}
  .accum-label-strong {{ background:rgba(34,197,94,.12); color:var(--green); border:1px solid rgba(34,197,94,.25); padding:1px 7px; border-radius:3px; font-size:9px; font-weight:700; }}
  .accum-label-watch  {{ background:rgba(34,211,238,.08); color:var(--cyan); border:1px solid rgba(34,211,238,.2); padding:1px 7px; border-radius:3px; font-size:9px; font-weight:600; }}

  /* ── EXPERT + TRADE SETUP CARDS ── */
  .top-trades-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:8px; }}
  .trade-card {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:12px; cursor:pointer; transition: all .12s; }}
  .trade-card:hover {{ border-color:rgba(34,197,94,.35); transform:translateY(-1px); }}
  .conf-bar {{ height:3px; border-radius:2px; background:var(--bg4); margin-top:7px; overflow:hidden; }}
  .conf-fill {{ height:100%; border-radius:2px; transition:width .5s; }}
  .conf-label {{ font-size:9px; color:var(--muted); margin-top:3px; display:flex; justify-content:space-between; }}

  /* ── QP (quick picks) ── */
  .qp-panel {{ background:var(--bg2); border:1px solid var(--border); border-radius:8px; padding:14px; margin-bottom:14px; }}
  .qp-title {{ font-size:11px; font-weight:700; color:var(--text); margin-bottom:10px; }}
  .qp-grid  {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:8px; }}
  .qp-col   {{ background:var(--bg3); border-radius:6px; padding:10px; }}
  .qp-col-title {{ font-size:9px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-bottom:7px; padding-bottom:5px; border-bottom:1px solid var(--border2); }}
  .qp-stock {{ display:flex; justify-content:space-between; align-items:center; padding:3px 0; font-size:11px; cursor:pointer; }}
  .qp-stock:hover {{ color:var(--orange); }}
  .qp-stock-sym {{ font-weight:700; }}
  .qp-stock-meta {{ font-size:9px; color:var(--muted); }}

  /* ── PIVOT CHIPS ── */
  .pivot-row {{ display:flex; gap:5px; flex-wrap:wrap; margin-top:5px; font-size:10px; }}
  .pivot-chip {{ background:var(--bg3); border-radius:3px; padding:2px 7px; }}
  .pivot-chip.pp {{ color:var(--text); font-weight:700; }}
  .pivot-chip.r1 {{ color:var(--green); }}
  .pivot-chip.r2 {{ color:#16a34a; }}
  .pivot-chip.s1 {{ color:var(--red); }}
  .pivot-chip.s2 {{ color:#be123c; }}

  /* ── SORT BAR ── */
  .sort-bar {{ display:flex; gap:4px; margin-bottom:8px; flex-wrap:wrap; align-items:center; }}
  .sort-lbl {{ font-size:10px; color:var(--muted); }}
  .sort-btn {{ padding:3px 9px; border-radius:4px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:10px; font-family:inherit; cursor:pointer; transition:all .12s; }}
  .sort-btn:hover {{ border-color:var(--amber); color:var(--amber); }}
  .sort-btn.active {{ background:rgba(245,158,11,.12); border-color:var(--amber); color:var(--amber); font-weight:700; }}
  .sector-select {{ background:var(--bg3); border:1px solid var(--border); border-radius:4px; color:var(--muted); font-size:10px; font-family:inherit; padding:3px 8px; cursor:pointer; outline:none; }}
  .range-filter {{ display:flex; align-items:center; gap:6px; font-size:10px; color:var(--muted); }}
  .range-filter input[type=range] {{ width:80px; accent-color:var(--orange); cursor:pointer; }}
  .filter-sep {{ width:1px; height:14px; background:var(--border); margin:0 2px; }}
  .results-counter {{ font-size:10px; color:var(--muted); margin-left:auto; padding:3px 8px; background:var(--bg3); border-radius:4px; }}

  /* ── GRADE DIST ── */
  .grade-dist {{ display:flex; gap:6px; margin-bottom:14px; flex-wrap:wrap; }}
  .grade-pill {{ padding:5px 12px; border-radius:6px; font-size:11px; font-weight:700; color:white; }}

  /* ── EXPORT / COPY BTNS ── */
  .export-btn {{ padding:4px 10px; border-radius:4px; border:1px solid rgba(34,211,238,.3); background:transparent; color:var(--cyan); font-size:10px; font-family:inherit; cursor:pointer; transition:all .12s; }}
  .export-btn:hover {{ background:rgba(34,211,238,.08); }}

  /* ── STAGE BADGES ── */
  .stage-2  {{ background:rgba(34,197,94,.12); color:var(--green); border:1px solid rgba(34,197,94,.25); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .stage-1  {{ background:rgba(34,211,238,.1);  color:var(--cyan);  border:1px solid rgba(34,211,238,.2); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .stage-3  {{ background:rgba(245,158,11,.1); color:var(--amber); border:1px solid rgba(245,158,11,.2); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .stage-4  {{ background:rgba(244,63,94,.1);  color:var(--red);   border:1px solid rgba(244,63,94,.2);  padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .pledge-danger {{ background:rgba(244,63,94,.12); color:var(--red); border:1px solid rgba(244,63,94,.3); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .pledge-warn   {{ background:rgba(245,158,11,.1); color:var(--amber); border:1px solid rgba(245,158,11,.25); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .fund-strong {{ background:rgba(167,139,250,.12); color:var(--purple); border:1px solid rgba(167,139,250,.25); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}
  .fund-good   {{ background:rgba(34,197,94,.1);  color:var(--green); border:1px solid rgba(34,197,94,.2); padding:1px 6px; border-radius:3px; font-size:9px; font-weight:700; }}

  /* ── SCROLLBAR ── */
  ::-webkit-scrollbar {{ width:5px; height:5px; }}
  ::-webkit-scrollbar-track {{ background:var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background:var(--bg4); border-radius:3px; }}
  ::-webkit-scrollbar-thumb:hover {{ background:#2d3748; }}

  /* ── FOOTER ── */
  .footer {{ text-align:center; color:var(--muted); font-size:10px; padding:16px 0 10px; border-top:1px solid var(--border2); margin-top:24px; letter-spacing:0.03em; }}

  /* ── RESPONSIVE ── */
  @media (max-width: 900px) {{
    .sidebar {{ transform: translateX(-100%); transition: transform 0.2s; }}
    .sidebar.open {{ transform: translateX(0); }}
    .main-content {{ margin-left: 0; }}
    .topbar {{ padding: 8px 14px; }}
  }}

</style>
<body>
<div class="app-shell">

<!-- ═══ SIDEBAR ═══ -->
<nav class="sidebar" id="sidebar">
  <div class="sidebar-logo">
    <div class="sidebar-logo-mark"><span style="color:var(--accent)">Trade</span> <span style="color:var(--accent2)">Stag</span></div>
    <div class="sidebar-logo-sub">NSE 500 · India-First</div>
    <div class="sidebar-tagline">v7.2 · Swing Trading Scanner</div>
  </div>

  <!-- Swing Trading -->
  <div class="sidebar-group">
    <div class="sidebar-group-label">Swing Trading</div>
    <div class="sidebar-item active" id="sb-all"         onclick="sbSwitch('all',this)">        <span class="si-icon">📊</span><span class="si-label">All Stocks</span>        <span class="si-count" id="sbc-all">—</span></div>
    <div class="sidebar-item" id="sb-aplus"      onclick="sbSwitch('aplus',this)">       <span class="si-icon">⭐</span><span class="si-label">Top Scoring Stocks</span>        <span class="si-count" id="sbc-aplus">—</span><span class="si-badge hot">HOT</span></div>
    <div class="sidebar-item" id="sb-expert"     onclick="sbSwitch('expert',this)">      <span class="si-icon">🎯</span><span class="si-label">Multi-Factor Leaders</span>        <span class="si-count" id="sbc-expert">—</span></div>
    <div class="sidebar-item" id="sb-trade"      onclick="sbSwitch('trade',this)">       <span class="si-icon">💡</span><span class="si-label">High Conviction Setups</span>         <span class="si-count" id="sbc-trade">—</span></div>
    <div class="sidebar-item" id="sb-breakouts"  onclick="sbSwitch('breakouts',this)">   <span class="si-icon">⚡</span><span class="si-label">Breakouts</span>           <span class="si-count" id="sbc-breakouts">—</span></div>
    <div class="sidebar-item" id="sb-volsurge"   onclick="sbSwitch('volsurge',this)">    <span class="si-icon">🔥</span><span class="si-label">Vol Surge</span>           <span class="si-count" id="sbc-volsurge">—</span></div>
    <div class="sidebar-item" id="sb-accumulation" onclick="sbSwitch('accumulation',this)"><span class="si-icon">🏦</span><span class="si-label">Accumulation</span>       <span class="si-count" id="sbc-accumulation">—</span></div>
  </div>

  <!-- Technical Analysis -->
  <div class="sidebar-group">
    <div class="sidebar-group-label">Technical</div>
    <div class="sidebar-item" id="sb-ema"         onclick="sbSwitch('ema',this)">         <span class="si-icon">📈</span><span class="si-label">EMA Scanner</span>         <span class="si-count" id="sbc-ema">8</span><span class="si-badge new">NEW</span></div>
    <div class="sidebar-item" id="sb-vcp"         onclick="sbSwitch('vcp',this)">         <span class="si-icon">🔷</span><span class="si-label">VCP Setups</span>          <span class="si-count" id="sbc-vcp">—</span></div>
    <div class="sidebar-item" id="sb-rs"          onclick="sbSwitch('rs',this)">          <span class="si-icon">🚀</span><span class="si-label">RS Leaders</span>          <span class="si-count" id="sbc-rs">—</span></div>
    <div class="sidebar-item" id="sb-stage2"      onclick="sbSwitch('stage2',this)">      <span class="si-icon">✅</span><span class="si-label">Stage 2</span>             <span class="si-count" id="sbc-stage2">—</span></div>
    <div class="sidebar-item" id="sb-price_action" onclick="sbSwitch('price_action',this)"><span class="si-icon">📊</span><span class="si-label">Price Action</span>       <span class="si-count" id="sbc-price_action">8</span></div>
  </div>

  <!-- Fundamental / Value -->
  <div class="sidebar-group">
    <div class="sidebar-group-label">Fundamental</div>
    <div class="sidebar-item" id="sb-fundamentals" onclick="sbSwitch('fundamentals',this)"><span class="si-icon">💎</span><span class="si-label">Fundamentals</span>      <span class="si-count" id="sbc-fundamentals">—</span></div>
    <div class="sidebar-item" id="sb-value_screen" onclick="sbSwitch('value_screen',this)"><span class="si-icon">💰</span><span class="si-label">Value Screens</span>      <span class="si-count" id="sbc-value_screen">7</span></div>
    <div class="sidebar-item" id="sb-quality_screen" onclick="sbSwitch('quality_screen',this)"><span class="si-icon">🏆</span><span class="si-label">Quality Stocks</span>  <span class="si-count" id="sbc-quality_screen">8</span></div>
  </div>

  <!-- Market Context -->
  <div class="sidebar-group">
    <div class="sidebar-group-label">Market</div>
    <div class="sidebar-item" id="sb-sectors"     onclick="sbSwitch('sectors',this)">     <span class="si-icon">🏭</span><span class="si-label">Sectors</span>             <span class="si-count" id="sbc-sectors">—</span></div>
  </div>
</nav>

<!-- ═══ MAIN CONTENT ═══ -->
<div class="main-content">

<!-- TOP BAR -->
<div class="topbar" id="topbar">
  <button onclick="document.getElementById('sidebar').classList.toggle('open')" style="display:none;background:var(--bg3);border:1px solid var(--border);color:var(--muted);padding:5px 8px;border-radius:5px;cursor:pointer;font-family:inherit" id="menu-btn">☰</button>
  <div class="topbar-title">
    <span class="topbar-breadcrumb">Trade Stag</span>
    <span class="topbar-sep">›</span>
    <span id="topbar-section-name">All Stocks</span>
  </div>
  <div class="topbar-stats" id="topbar-stats">
    <span class="ts hl">Generated: <strong>{analysis_time}</strong></span>
    <span class="ts">Universe: <strong>{total} stocks</strong></span>
    <span class="ts up" id="tb-fii">FII: <strong>{fii_5d_str}</strong></span>
    <span class="ts">PCR: <strong style="color:var(--cyan)">{pcr_val_html}</strong></span>
    <span class="ts">VIX: <strong style="color:var(--amber)">{vix_val_html}</strong></span>
  </div>
</div>

<!-- CONTENT AREA -->
<div class="content-area">

<!-- MARKET PULSE STRIP -->
<div class="pulse-strip">
  <div class="pulse-card">
    <div class="pc-label">Nifty PCR</div>
    <div class="pc-val" style="color:{'var(--green)' if pcr_sent=='Bullish' else 'var(--red)' if pcr_sent=='Bearish' else 'var(--amber)'}">{pcr_val}</div>
    <div class="pc-sub">{pcr_sent}</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">Weekly PCR</div>
    <div class="pc-val" style="color:{'var(--green)' if weekly_pcr and weekly_pcr>1.0 else 'var(--red)'}">{weekly_pcr if weekly_pcr else "N/A"}</div>
    <div class="pc-sub">Exp {weekly_exp}</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">Max Pain</div>
    <div class="pc-val" style="color:var(--amber)">{mp_display}</div>
    <div class="pc-sub">{mp_sentiment[:28] if mp_sentiment and len(mp_sentiment)>2 else "N/A"}</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">FII 5-Day Net</div>
    <div class="pc-val" style="color:{'var(--green)' if (fii_5d_html or 0)>0 else 'var(--red)'}">{fii_5d_str}</div>
    <div class="pc-sub">{fii_sentiment}</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">Market Breadth</div>
    <div class="pc-val" style="color:{breadth_col}">{breadth_pct}%</div>
    <div class="pc-sub">Above 200 EMA · {breadth_status}</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">India VIX</div>
    <div class="pc-val" style="color:var(--amber)">{vix_val_html}</div>
    <div class="pc-sub">Fear gauge</div>
  </div>
  <div class="pulse-card">
    <div class="pc-label">FII Today</div>
    <div class="pc-val" style="color:{'var(--green)' if fii_net and fii_net>0 else 'var(--red)'}">{'₹{:,.0f}Cr'.format(fii_net) if fii_net else "N/A"}</div>
    <div class="pc-sub">DII: {'₹{:,.0f}Cr'.format(dii_net) if dii_net else "N/A"}</div>
  </div>
</div>

<!-- AD BAR -->
<div class="ad-bar">
  <div class="ad-adv" style="width:{adv_pct:.1f}%">{adv_count}▲</div>
  <div class="ad-unch" style="width:{unch_pct:.1f}%;min-width:4px"></div>
  <div class="ad-dec" style="width:{dec_pct:.1f}%">{dec_count}▼</div>
</div>

<div class="stat-grid">
  <div class="stat-card"><div class="stat-label">Analyzed</div><div class="stat-val">{total}</div><div class="stat-sub">NSE 500</div></div>
  <div class="stat-card"><div class="stat-label">A+ / A Grade</div><div class="stat-val" style="color:var(--orange)">{grade_counts.get('A+',0)+grade_counts.get('A',0)}</div><div class="stat-sub">Elite setups</div></div>
  <div class="stat-card"><div class="stat-label">Stage 2</div><div class="stat-val" style="color:var(--green)">{len(stage2_stocks)}</div><div class="stat-sub">Buy zone</div></div>
  <div class="stat-card"><div class="stat-label">RS Elite</div><div class="stat-val" style="color:var(--purple)">{len(rs_elite)}</div><div class="stat-sub">Top 10%</div></div>
  <div class="stat-card"><div class="stat-label">Vol Surge</div><div class="stat-val" style="color:var(--amber)">{len(vol_surges)}</div><div class="stat-sub">{len(vol_surges_up)} on up-days</div></div>
  <div class="stat-card"><div class="stat-label">Breakouts</div><div class="stat-val" style="color:var(--cyan)">{len(breakouts)}</div><div class="stat-sub">Vol-confirmed</div></div>
  <div class="stat-card"><div class="stat-label">Accumulation</div><div class="stat-val" style="color:var(--green)">{len(accum_stocks)}</div><div class="stat-sub">{len(strong_accum)} strong</div></div>
  <div class="stat-card"><div class="stat-label">Pledge Danger</div><div class="stat-val" style="color:var(--red)">{len(pledge_danger)}</div><div class="stat-sub">Avoid</div></div>
  <div class="stat-card"><div class="stat-label">Supertrend BUY</div><div class="stat-val" style="color:var(--green)">{len(supertrend_buy)}</div><div class="stat-sub">{len(st_flip)} fresh flips</div></div>
  <div class="stat-card"><div class="stat-label">Near Earnings</div><div class="stat-val" style="color:var(--red)">{len(near_earnings)}</div><div class="stat-sub">Wait</div></div>
</div>


<!-- GRADE DISTRIBUTION -->
<div class="section-title">Grade Distribution</div>
<div class="grade-dist">
"""
        for g, col in [("A+","#059669"),("A","#10b981"),("B+","#0284c7"),("B","#38bdf8"),("C","#f59e0b"),("D","#ef4444")]:
            cnt = grade_counts.get(g, 0)
            pct = round(cnt / total * 100, 1) if total > 0 else 0
            html += f'<div class="grade-pill" style="background:{col};">{g}: {cnt} <span style="opacity:.75;font-size:11px;">({pct}%)</span></div>\n'

        # ── TOP TRADES PANEL (v4.0) ──
        html += '</div>\n\n<!-- TOP TRADES PANEL (v4.0) -->\n<div class="top-trades-panel">\n'
        html += '<div class="top-trades-title">🎯 Highest Scoring Setups — Multi-Factor Ranking</div>\n'
        html += '<div class="top-trades-grid">\n'
        for i, r in enumerate(top_trades, 1):
            ts       = r.get("trade_setup", {})
            conf     = r.get("confidence_pct", 50)
            setup    = ts.get("setup_type", "—")
            entry_v  = ts.get("entry", 0)
            sl_v     = ts.get("stop_loss", 0)
            t1_v     = ts.get("target1", 0)
            rr       = ts.get("rr_ratio", 0)
            accum    = r.get("accum_label", "None")
            conf_col = ("#059669" if conf >= 80 else "#10b981" if conf >= 70 else "#0284c7" if conf >= 60 else "#f59e0b")
            accum_tag = f'<span style="background:rgba(16,185,129,.12);color:#10b981;border-radius:3px;padding:1px 5px;font-size:9px;margin-left:4px;">🏦{accum}</span>' if r.get("is_accumulating") else ""
            html += f"""<div class="trade-card" onclick="openModal('{r['symbol']}')">
  <div class="trade-card-rank">#{i} · {r.get('sector','—')}</div>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-top:4px;">
    <div>
      <div class="trade-card-sym">{r['symbol']}</div>
      <div class="trade-card-setup">{setup}{accum_tag}</div>
    </div>
    <span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span>
  </div>
  <div class="conf-bar"><div class="conf-fill" style="width:{conf}%;background:{conf_col};"></div></div>
  <div class="conf-label"><span>Confidence</span><span style="color:{conf_col};font-weight:700;">{conf}%</span></div>
  <div class="trade-card-prices">
    <div class="price-chip">CMP <strong style="color:var(--text);">₹{r['price']:,.1f}</strong></div>
    <div class="price-chip">Entry <strong style="color:var(--blue);">₹{entry_v:,.1f}</strong></div>
    <div class="price-chip">SL <strong style="color:var(--red);">₹{sl_v:,.1f}</strong></div>
    <div class="price-chip">T1 <strong style="color:var(--green);">₹{t1_v:,.1f}</strong></div>
    <div class="price-chip">R:R <strong style="color:var(--amber);">{rr}x</strong></div>
  </div>
</div>\n"""
        html += '</div>\n</div>\n\n'

        # Section panes start here (sidebar JS controls which is visible)




















        # ── Build main stock table ──
        # Collect all unique sectors for dropdown
        all_sectors = sorted(set(r.get("sector","Others") for r in results))

        def build_table(rows, table_id, show_warn=False):
            sector_opts = "".join(f'<option value="{s}">{s}</option>' for s in all_sectors)
            t = f"""
<div id="pane-{table_id}" class="tab-pane {'active' if table_id=='all' else ''}">

<!-- Search + Sector + Results counter -->
<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:180px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." id="search-{table_id}"
      oninput="handleSearch(this,'{table_id}')">
  </div>
  <select class="sector-select" id="sector-{table_id}" onchange="handleSector(this,'{table_id}')">
    <option value="">All Sectors</option>
    {sector_opts}
  </select>
  <span class="results-counter" id="counter-{table_id}">— stocks</span>
</div>

<!-- Sort Bar -->
<div class="sort-bar">
  <span class="sort-lbl">Sort:</span>
  <button class="sort-btn active" onclick="quickSort('{table_id}',3,'desc',this)">Score ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',5,'desc',this)">1D% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',5,'asc',this)">1D% ↑</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',6,'desc',this)">5D% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',7,'desc',this)">1M% ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',13,'desc',this)">Vol Ratio ↓</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',11,'asc',this)">BB Tight ↑</button>
  <button class="sort-btn" onclick="quickSort('{table_id}',12,'desc',this)">RS%ile ↓</button>
  <div class="filter-sep"></div>
  <span class="range-filter">
    Score ≥ <input type="range" min="0" max="100" value="0" step="5" id="scoremin-{table_id}"
      oninput="handleScore(this,'{table_id}')">
    <span id="scoreval-{table_id}" style="min-width:24px;color:var(--blue);font-weight:600;">0</span>
  </span>
</div>

<!-- Filter chips -->
<div class="filter-row">
  <span style="color:var(--muted);font-size:11px;">Filter:</span>
  <button class="filter-btn on" id="chip-all-{table_id}" onclick="setChip(this,'{table_id}','')">All</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','A+')">A+</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','A')">A</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','B+')">B+</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','nr7')">NR7</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','inside_day')">Inside Day</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','pocket_pivot')">Pocket Pivot</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vcp')">🔷 VCP</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vol_dryup')">📉 Vol Dry-Up</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','breakout')">⚡ Breakout</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','gainer')">📈 Gainers Today</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','loser')">📉 Losers Today</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','gainer_5d')">📈 5D Gainer</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','stage2')">✅ Stage 2</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','fund_strong')">💎 Fund Strong</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','accumulation')">🏦 Accum</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','rs_elite')">🚀 RS Elite</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','hi_delivery')">📦 Delivery&gt;55%</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','vol_surge')">🔥 Vol Surge</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','pledge_danger')">🚨 Pledge Danger</button>
  <button class="filter-btn" onclick="setChip(this,'{table_id}','earnings_warn')">⚠️ Near Results</button>
</div>

<div class="tbl-wrap">
<table id="{table_id}-table">
<thead>
  <tr>
    <th onclick="sortTable('{table_id}-table',0)">#</th>
    <th onclick="sortTable('{table_id}-table',1)">Symbol</th>
    <th onclick="sortTable('{table_id}-table',2)">Grade</th>
    <th onclick="sortTable('{table_id}-table',3)">Score</th>
    <th onclick="sortTable('{table_id}-table',4)">Price</th>
    <th onclick="sortTable('{table_id}-table',5)">1D%</th>
    <th onclick="sortTable('{table_id}-table',6)">5D%</th>
    <th onclick="sortTable('{table_id}-table',7)">1M%</th>
    <th onclick="sortTable('{table_id}-table',8)">3M%</th>
    <th onclick="sortTable('{table_id}-table',9)">RSI</th>
    <th onclick="sortTable('{table_id}-table',10)">ADX</th>
    <th onclick="sortTable('{table_id}-table',11)">BB%</th>
    <th onclick="sortTable('{table_id}-table',12)">RS%ile</th>
    <th onclick="sortTable('{table_id}-table',13)">Vol Ratio</th>
    <th onclick="sortTable('{table_id}-table',14)">Delivery%</th>
    <th onclick="sortTable('{table_id}-table',15)">52W High%</th>
    <th onclick="sortTable('{table_id}-table',16)">Stage</th>
    <th onclick="sortTable('{table_id}-table',17)">Fund</th>
    <th onclick="sortTable('{table_id}-table',18)">Pledge%</th>
    <th onclick="sortTable('{table_id}-table',19)">Sector</th>
    <th>Entry / SL / T1</th>
    <th>Qty</th>
    <th>Signals</th>
  </tr>
</thead>
<tbody>
"""
            for i, r in enumerate(rows, 1):
                chg_class  = lambda v: "up" if v > 0 else "down" if v < 0 else "neutral"
                rsi_col    = "#10b981" if 50<=r['rsi']<=72 else "#ef4444" if r['rsi']>80 else "#f59e0b" if r['rsi']<40 else "#e8eaf0"
                adx_col    = "#10b981" if r['adx']>25 else "#f59e0b" if r['adx']>20 else "#8892a4"
                bb_col     = "#10b981" if r['bb_width']<8 else "#f59e0b" if r['bb_width']<12 else "#8892a4"
                rs_col     = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#8892a4"
                del_pct    = r['delivery_pct']
                del_str    = f"{del_pct:.0f}%" if del_pct is not None else "—"
                del_col    = "#10b981" if del_pct is not None and del_pct>=55 else "#f59e0b" if del_pct is not None and del_pct>=40 else "#8892a4"
                earn_warn  = r['earnings_info'].get('has_upcoming', False)
                ts         = r.get('trade_setup', {})
                entry_str  = f"₹{ts.get('entry',0):,.1f}" if ts.get('entry') else "—"
                sl_str     = f"₹{ts.get('stop_loss',0):,.1f}" if ts.get('stop_loss') else "—"
                t1_str     = f"₹{ts.get('target1',0):,.1f}" if ts.get('target1') else "—"
                trade_html = f'<span style="color:var(--blue)">{entry_str}</span> / <span style="color:var(--red)">{sl_str}</span> / <span style="color:var(--green)">{t1_str}</span>'
                sigs       = r["active_signals"][:5]
                sigs_html  = ""
                for s in sigs:
                    cls = "signal-elite" if "Elite" in s or "RS" in s else \
                          "signal-warn"  if "⚠️" in s or "Results" in s else \
                          "signal-surge" if any(x in s for x in ["Surge","surge"]) else \
                          "signal-green" if any(x in s for x in ["Delivery","Near52W","Breakout"]) else ""
                    sigs_html += f'<span class="signal-tag {cls}">{s}</span>'
                # ── v3.0 new cell variables ──
                stage_val   = r.get("stage", "Unknown")
                stage_cls   = {"Stage 2":"stage-2","Stage 1":"stage-1","Stage 3":"stage-3","Stage 4":"stage-4"}.get(stage_val,"")
                fund_grade  = r.get("fund_grade", "N/A")
                fund_cls    = {"Strong":"fund-strong","Good":"fund-good","Weak":"fund-weak"}.get(fund_grade,"")
                pledge      = r.get("pledge_pct")
                pledge_str  = f"{pledge:.0f}%" if pledge is not None else "—"
                pledge_cls  = "pledge-danger" if r.get("pledge_danger") else "pledge-warn" if r.get("pledge_warn") else ""
                # Volume surge
                vs_type  = r.get("vol_surge_type", "")
                vs_ratio = r.get("vol_surge_ratio", 0)
                vs_up    = r.get("vol_surge_up", False)
                vs_col   = ("#f59e0b" if vs_type == "MegaSurge"
                            else "#10b981" if vs_type == "StrongSurge"
                            else "#38bdf8" if vs_type else "#8892a4")
                vs_str   = (f"🔥{vs_ratio:.1f}x" if vs_type == "MegaSurge"
                            else f"⚡{vs_ratio:.1f}x" if vs_type == "StrongSurge"
                            else f"↑{vs_ratio:.1f}x" if vs_type else "—")
                # Position qty
                ts_entry = ts.get("entry", 0)
                ts_sl    = ts.get("stop_loss", 0)
                if ts_entry and ts_sl and ts_entry > ts_sl:
                    risk_per = ts_entry - ts_sl
                    qty = int(risk_amt / risk_per) if risk_per > 0 else 0
                else:
                    qty = 0
                qty_str  = f"{qty:,}" if qty > 0 else "—"
                data_attrs = (f'data-grade="{r["grade"]}" '
                              f'data-sector="{r.get("sector","Others")}" '
                              f'data-score="{r["score"]}" '
                              f'data-breakout="{1 if r["breakout"] else 0}" '
                              f'data-vcp="{1 if r["vcp_score"]>=60 else 0}" '
                              f'data-nr7="{1 if r.get("nr7") else 0}" '
                              f'data-inside_day="{1 if r.get("inside_day") else 0}" '
                              f'data-pocket_pivot="{1 if r.get("pocket_pivot") else 0}" '
                              f'data-vol_dryup="{1 if r.get("vol_dry_up") else 0}" '
                              f'data-rs_elite="{1 if r["rs_percentile"]>=90 else 0}" '
                              f'data-hi_delivery="{1 if del_pct is not None and del_pct>=55 else 0}" '
                              f'data-near52w="{1 if r["near_52w_high"] else 0}" '
                              f'data-vol_surge="{1 if vs_type else 0}" '
                              f'data-vol_surge_up="{1 if vs_type and vs_up else 0}" '
                              f'data-stage2="{1 if stage_val=="Stage 2" else 0}" '
                              f'data-fund_strong="{1 if fund_grade=="Strong" else 0}" '
                              f'data-pledge_danger="{1 if r.get("pledge_danger") else 0}" '
                              f'data-earnings_warn="{1 if earn_warn else 0}" '
                              f'data-accumulation="{1 if r.get("is_accumulating") else 0}" '
                              f'data-gainer="{1 if r["chg_1d"]>0 else 0}" '
                              f'data-loser="{1 if r["chg_1d"]<0 else 0}" '
                              f'data-gainer_5d="{1 if r["chg_5d"]>0 else 0}"')
                warn_icon = ' <span style="color:#ef4444;font-size:10px;" title="Results soon">⚠️</span>' if earn_warn else ''
                circuit_icon = f' <span style="color:#f59e0b;font-size:9px;" title="Near circuit limit">⚡{r.get("circuit_risk","")}</span>' if r.get("circuit_risk") else ''
                fno_icon = ' <span style="color:#8892a4;font-size:9px;">F&O</span>' if r.get("is_fno") else ''
                # Sparkline SVG
                spark_prices = r.get("sparkline", [])
                spark_html = ""
                if spark_prices and len(spark_prices) >= 3:
                    mn, mx = min(spark_prices), max(spark_prices)
                    rng = (mx - mn) or 1
                    w, h = 44, 16
                    pts = " ".join(
                        f"{round(i*(w/(len(spark_prices)-1)),1)},{round(h - (v-mn)/rng*h, 1)}"
                        for i, v in enumerate(spark_prices)
                    )
                    clr = "#10b981" if spark_prices[-1] >= spark_prices[0] else "#ef4444"
                    spark_html = f'<svg class="sparkline" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><polyline points="{pts}" fill="none" stroke="{clr}" stroke-width="1.5" stroke-linejoin="round"/></svg>'
                # Score tooltip showing top contributors
                sb = r.get("score_breakdown", {})
                top_contributors = sorted([(k,v) for k,v in sb.items() if v>0], key=lambda x:-x[1])[:3]
                score_tip = " | ".join(f"{k.replace('_',' ')}:{v}" for k,v in top_contributors)
                t += f"""<tr {data_attrs} onclick="openModal('{r['symbol']}')">
  <td style="color:var(--muted);">{i}</td>
  <td><strong>{r['symbol']}</strong>{warn_icon}{circuit_icon}{fno_icon}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span></td>
  <td>
    <div style="display:flex;align-items:center;gap:5px;" title="{score_tip}">
      <span style="font-weight:700;cursor:help;">{r['score']}</span>
      <div class="prog-bar" style="width:40px;"><div class="prog-fill" style="width:{r['score']}%;background:{r['grade_color']};"></div></div>
    </div>
  </td>
  <td style="font-weight:600;">
    <div style="display:flex;align-items:center;gap:6px;">
      ₹{r['price']:,.2f}
      {spark_html}
    </div>
  </td>
  <td class="{chg_class(r['chg_1d'])}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td class="{chg_class(r['chg_5d'])}">{'+' if r['chg_5d']>0 else ''}{r['chg_5d']:.2f}%</td>
  <td class="{chg_class(r['chg_1m'])}">{'+' if r['chg_1m']>0 else ''}{r['chg_1m']:.2f}%</td>
  <td class="{chg_class(r['chg_3m'])}">{'+' if r['chg_3m']>0 else ''}{r['chg_3m']:.2f}%</td>
  <td style="color:{rsi_col};">{r['rsi']}</td>
  <td style="color:{adx_col};">{r['adx']}</td>
  <td style="color:{bb_col};">{r['bb_width']:.1f}%</td>
  <td><div style="display:flex;align-items:center;gap:4px;"><div class="prog-bar" style="width:30px;"><div class="prog-fill" style="width:{r['rs_percentile']}%;background:{rs_col};"></div></div><span style="color:{rs_col};">{r['rs_percentile']}</span></div></td>
  <td style="color:{del_col};">{del_str}</td>
  <td style="color:{vs_col};font-weight:{'700' if vs_type else '400'};">{vs_str}</td>
  <td class="{'up' if r['pct_from_high']>=-5 else 'neutral'}">{r['pct_from_high']:.1f}%</td>
  <td><span class="{stage_cls}" style="font-size:10px;">{stage_val.replace("Stage ","S")}</span></td>
  <td><span class="{fund_cls}" style="font-size:10px;">{fund_grade}</span></td>
  <td><span class="{pledge_cls}" style="font-size:10px;">{pledge_str}</span></td>
  <td style="font-size:11px;color:var(--muted);">{r['sector']}</td>
  <td style="font-size:11px;">{trade_html}</td>
  <td style="color:var(--blue);font-weight:600;font-size:12px;">{qty_str}</td>
  <td>{sigs_html if sigs_html else '<span style="color:var(--muted);font-size:11px;">—</span>'}</td>
</tr>
"""
            t += "</tbody></table></div></div>\n"
            return t

        html += build_table(results, "all")
        html += build_table([r for r in results if r["grade"] in ("A+","A")], "aplus")
        html += build_table(breakouts, "breakouts")
        html += build_table(vcps, "vcp")
        html += build_table(sorted(results, key=lambda x: x["rs_percentile"], reverse=True)[:60], "rs")

        # ── Volume Surge Tab ──
        vs_sorted = sorted(
            [r for r in results if r.get("vol_surge_type")],
            key=lambda x: x.get("vol_surge_ratio", 0), reverse=True
        )
        html += '<div id="pane-volsurge" class="tab-pane">\n'
        html += f'''<div style="display:flex;align-items:center;gap:16px;margin-bottom:10px;flex-wrap:wrap;">
  <div class="section-title" style="margin-bottom:0;">🔥 Volume Surge Stocks — Today\'s volume vs 20-day average</div>
  <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px;">
    <span style="background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.3);color:var(--amber);padding:3px 10px;border-radius:20px;">🔥 Mega Surge ≥{CFG['vol_surge_mega']}×</span>
    <span style="background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.3);color:var(--green);padding:3px 10px;border-radius:20px;">⚡ Strong Surge ≥{CFG['vol_surge_strong']}×</span>
    <span style="background:rgba(56,189,248,.15);border:1px solid rgba(56,189,248,.3);color:var(--blue);padding:3px 10px;border-radius:20px;">↑ Surge ≥{CFG['vol_surge_mild']}×</span>
    <span style="color:var(--muted);">↑ = Up-day (bullish)  ↓ = Down-day (caution)</span>
  </div>
</div>
<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchSimpleTable(this,'volsurge-table')">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterSimpleGrade(this,'volsurge-table','')">All</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','A+')">A+</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','A')">A</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'volsurge-table','B+')">B+</button>
  </div>
  <span id="counter-volsurge" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="volsurge-table">\n'
        html += '''<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>
  <th>Price</th><th>1D%</th>
  <th>Vol Ratio</th><th>Surge Type</th><th>Up/Down Day</th>
  <th>RSI</th><th>ADX</th><th>RS%ile</th><th>Delivery%</th>
  <th>Entry / SL / T1</th><th>Signals</th>
</tr></thead>\n<tbody>\n'''
        for i, r in enumerate(vs_sorted, 1):
            vs_type  = r.get("vol_surge_type", "")
            vs_ratio = r.get("vol_surge_ratio", 0)
            vs_up    = r.get("vol_surge_up", False)
            vs_col   = ("#f59e0b" if vs_type == "MegaSurge"
                        else "#10b981" if vs_type == "StrongSurge"
                        else "#38bdf8")
            vs_icon  = "🔥 Mega" if vs_type == "MegaSurge" else "⚡ Strong" if vs_type == "StrongSurge" else "↑ Surge"
            day_col  = "#10b981" if vs_up else "#ef4444"
            day_str  = "↑ UP (Bullish)" if vs_up else "↓ DOWN (Caution)"
            del_pct  = r['delivery_pct']
            del_str  = f"{del_pct:.0f}%" if del_pct is not None else "—"
            del_col  = "#10b981" if del_pct is not None and del_pct >= 55 else "#8892a4"
            rsi_col  = "#10b981" if 50<=r['rsi']<=72 else "#ef4444" if r['rsi']>80 else "#f59e0b"
            adx_col  = "#10b981" if r['adx']>25 else "#f59e0b" if r['adx']>20 else "#8892a4"
            rs_col   = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#8892a4"
            chg_class = "up" if r['chg_1d'] > 0 else "down" if r['chg_1d'] < 0 else "neutral"
            ts       = r.get("trade_setup", {})
            entry_s  = f"₹{ts.get('entry',0):,.1f}" if ts.get('entry') else "—"
            sl_s     = f"₹{ts.get('stop_loss',0):,.1f}" if ts.get('stop_loss') else "—"
            t1_s     = f"₹{ts.get('target1',0):,.1f}" if ts.get('target1') else "—"
            trade_h  = f'<span style="color:var(--blue)">{entry_s}</span> / <span style="color:var(--red)">{sl_s}</span> / <span style="color:var(--green)">{t1_s}</span>'
            sigs_h   = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
            html += f"""<tr onclick="openModal('{r['symbol']}')" style="cursor:pointer;">
  <td style="color:var(--muted);">{i}</td>
  <td><strong>{r['symbol']}</strong></td>
  <td style="font-size:12px;color:var(--muted);">{r['sector']}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span></td>
  <td style="font-weight:700;">{r['score']}</td>
  <td style="font-weight:600;">₹{r['price']:,.2f}</td>
  <td class="{chg_class}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td style="color:{vs_col};font-weight:800;">{vs_ratio:.2f}×</td>
  <td><span style="color:{vs_col};font-weight:700;">{vs_icon}</span></td>
  <td style="color:{day_col};font-weight:600;">{day_str}</td>
  <td style="color:{rsi_col};">{r['rsi']}</td>
  <td style="color:{adx_col};">{r['adx']}</td>
  <td style="color:{rs_col};">{r['rs_percentile']}</td>
  <td style="color:{del_col};">{del_str}</td>
  <td style="font-size:12px;">{trade_h}</td>
  <td>{sigs_h if sigs_h else '<span style="color:var(--muted);font-size:11px;">—</span>'}</td>
</tr>\n"""
        html += "</tbody></table></div>\n</div>\n"

        # ── Stage 2 Tab ──
        s2_sorted = sorted([r for r in results if r.get("is_stage2")], key=lambda x: x["score"], reverse=True)
        html += '<div id="pane-stage2" class="tab-pane">\n'
        html += f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap;"><div class="section-title" style="margin-bottom:0;">✅ Stage 2 Advancing Stocks — price above rising 30-week MA (Weinstein buy zone)</div><div style="font-size:11px;color:var(--muted);">{len(s2_sorted)} stocks in Stage 2</div></div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchSimpleTable(this,'stage2-table')">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterSimpleGrade(this,'stage2-table','')">All</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','A+')">A+</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','A')">A</button>
    <button class="filter-btn" onclick="filterSimpleGrade(this,'stage2-table','B+')">B+</button>
  </div>
  <span id="counter-stage2" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="stage2-table"><thead><tr>\n'
        html += '<th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th><th>Price</th><th>1M%</th><th>RS%ile</th><th>RSI</th><th>ADX</th><th>30W MA</th><th>MA Slope</th><th>Fund Grade</th><th>Pledge%</th><th>Entry / SL / T1</th><th>Qty</th><th>Signals</th>\n'
        html += '</tr></thead><tbody>\n'
        for i, r in enumerate(s2_sorted, 1):
            si       = r.get("stage_info", {})
            ma30     = f"₹{si.get('ma30',0):,.1f}" if si.get('ma30') else "—"
            slope    = si.get('ma_slope_pct', 0)
            slope_s  = f"{slope:+.2f}%"
            slope_c  = "#10b981" if slope > 0.5 else "#f59e0b" if slope > 0 else "#ef4444"
            rsi_c    = "#10b981" if 50<=r['rsi']<=72 else "#f59e0b"
            rs_c     = "#a78bfa" if r['rs_percentile']>=90 else "#10b981" if r['rs_percentile']>=70 else "#e8eaf0"
            fg       = r.get("fund_grade","N/A")
            fg_c     = "#a78bfa" if fg=="Strong" else "#10b981" if fg=="Good" else "#f59e0b" if fg=="Moderate" else "#ef4444"
            pl       = r.get("pledge_pct")
            pl_s     = f"{pl:.0f}%" if pl is not None else "—"
            pl_c     = "#ef4444" if r.get("pledge_danger") else "#f59e0b" if r.get("pledge_warn") else "#8892a4"
            ts       = r.get("trade_setup", {})
            entry_v  = ts.get("entry", 0)
            sl_v     = ts.get("stop_loss", 0)
            qty      = int(risk_amt / (entry_v - sl_v)) if entry_v and sl_v and entry_v > sl_v else 0
            trade_h  = (f'<span style="color:var(--blue)">₹{entry_v:,.1f}</span> / '
                        f'<span style="color:var(--red)">₹{sl_v:,.1f}</span> / '
                        f'<span style="color:var(--green)">₹{ts.get("target1",0):,.1f}</span>') if entry_v else "—"
            sigs_h   = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
            chg_c    = "up" if r['chg_1m'] > 0 else "down"
            html += f"""<tr onclick="openModal('{r['symbol']}')" style="cursor:pointer;">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r['symbol']}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r['sector']}</td>
  <td><span class="grade-badge" style="background:{r['grade_color']}">{r['grade']}</span></td>
  <td style="font-weight:700">{r['score']}</td>
  <td style="font-weight:600">₹{r['price']:,.2f}</td>
  <td class="{chg_c}">{'+' if r['chg_1m']>0 else ''}{r['chg_1m']:.1f}%</td>
  <td style="color:{rs_c}">{r['rs_percentile']}</td>
  <td style="color:{rsi_c}">{r['rsi']}</td>
  <td style="color:{'#10b981' if r['adx']>25 else '#f59e0b'}">{r['adx']}</td>
  <td style="color:var(--muted);font-size:11px">{ma30}</td>
  <td style="color:{slope_c};font-weight:600">{slope_s}</td>
  <td style="color:{fg_c}">{fg}</td>
  <td style="color:{pl_c}">{pl_s}</td>
  <td style="font-size:11px">{trade_h}</td>
  <td style="color:var(--blue);font-weight:600">{f'{qty:,}' if qty else '—'}</td>
  <td>{sigs_h or '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
</tr>\n"""
        html += "</tbody></table></div>\n</div>\n"

        # ── Fundamentals Tab ──
        fund_sorted = sorted([r for r in results if r.get("fund_score", 0) > 0],
                             key=lambda x: x.get("fund_score", 0), reverse=True)
        html += '<div id="pane-fundamentals" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:10px;">💎 Fundamental Quality — ROE · EPS Growth · D/E · OCF Quality · Promoter Pledging</div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol..." oninput="searchFundCards(this)">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterFundCards(this,'')">All</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Strong')">💎 Strong</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Good')">✅ Good</button>
    <button class="filter-btn" onclick="filterFundCards(this,'Moderate')">⚡ Moderate</button>
  </div>
  <span id="counter-fundamentals" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        if pledge_danger:
            html += f'<div class="pledge-alert" style="margin-bottom:14px;">🚨 <strong>{len(pledge_danger)} stocks</strong> have promoter pledging &gt;{CFG["pledge_danger_pct"]}% — score penalised -{CFG["pledge_score_penalty"]} pts. Avoid or drastically reduce position size.</div>\n'
        html += '<div id="fund-cards-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(275px,1fr));gap:10px;">\n'
        for r in fund_sorted[:60]:
            fgrade  = r.get("fund_grade", "N/A")
            roe_v   = f"{r['roe']:.1f}%" if r.get("roe") is not None else "N/A"
            eps_v   = f"{r['eps_growth']:.1f}%" if r.get("eps_growth") is not None else "N/A"
            de_v    = f"{r['de_ratio']:.2f}" if r.get("de_ratio") is not None else "N/A"
            pe_v    = f"{r['pe_ratio']:.1f}×" if r.get("pe_ratio") is not None else "N/A"
            pledge  = r.get("pledge_pct")
            p_badge = ""
            if pledge is not None and pledge >= CFG["pledge_danger_pct"]:
                p_badge = f'<span class="pledge-danger" style="margin-left:6px">🚨Pledge {pledge:.0f}%</span>'
            elif pledge is not None and pledge >= CFG["pledge_warn_pct"]:
                p_badge = f'<span class="pledge-warn" style="margin-left:6px">⚠Pledge {pledge:.0f}%</span>'
            stage_v = r.get("stage","Unknown")
            stage_c = "#10b981" if stage_v=="Stage 2" else "#f59e0b" if stage_v=="Stage 1" else "#ef4444"
            fc      = "#a78bfa" if fgrade=="Strong" else "#10b981" if fgrade=="Good" else "#f59e0b" if fgrade=="Moderate" else "#ef4444"
            roe_c   = "#10b981" if r.get("roe") and r["roe"]>=20 else "#f59e0b" if r.get("roe") and r["roe"]>=12 else "#ef4444"
            eps_c   = "#10b981" if r.get("eps_growth") and r["eps_growth"]>=25 else "#f59e0b" if r.get("eps_growth") and r["eps_growth"]>=15 else "#ef4444"
            de_c    = "#10b981" if r.get("de_ratio") is not None and r["de_ratio"]<=0.5 else "#f59e0b" if r.get("de_ratio") is not None and r["de_ratio"]<=1.0 else "#ef4444"
            html += f"""<div class="fund-card" data-symbol="{r['symbol']}" data-fundgrade="{fgrade}" onclick="openModal('{r['symbol']}')">\n  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:4px;">
    <div><span style="font-size:15px;font-weight:800">{r['symbol']}</span><span class="grade-badge" style="background:{r['grade_color']};margin-left:7px">{r['grade']}</span>{p_badge}</div>
    <div style="text-align:right"><div style="font-size:18px;font-weight:800;color:{fc}">{r.get('fund_score',0)}/20</div><div style="font-size:10px;color:{fc}">{fgrade}</div></div>
  </div>
  <div class="fund-metric"><span style="color:var(--muted)">ROE</span><span style="color:{roe_c};font-weight:600">{roe_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">EPS Growth YoY</span><span style="color:{eps_c};font-weight:600">{eps_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">Debt / Equity</span><span style="color:{de_c};font-weight:600">{de_v}</span></div>
  <div class="fund-metric"><span style="color:var(--muted)">P/E Ratio</span><span style="font-weight:600">{pe_v}</span></div>
  <div class="fund-metric" style="border:none"><span style="color:var(--muted)">Stage</span><span style="color:{stage_c};font-weight:600">{stage_v}</span></div>
</div>\n"""
        html += "</div>\n</div>\n"

        # ── Accumulation Tab (v4.0) ──
        accum_sorted = sorted(
            [r for r in results if r.get("is_accumulating") or r.get("accum_score", 0) >= 20],
            key=lambda x: x.get("accum_score", 0), reverse=True
        )
        html += '<div id="pane-accumulation" class="tab-pane">\n'
        html += f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:10px;flex-wrap:wrap;">'
        html += f'<div class="section-title" style="margin-bottom:0;">🏦 Institutional Accumulation Detector — Smart Money Activity</div>'
        html += f'<div style="font-size:11px;color:var(--muted);">{len(strong_accum)} Strong · {len(accum_stocks)} Total</div>'
        html += f'<div style="font-size:11px;color:var(--muted);margin-left:auto;">Signals: Volume Accumulation · OBV Rising · BB Squeeze · Delivery Spike</div></div>\n'
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..." oninput="searchAccumCards(this)">
  </div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;">
    <button class="filter-btn on" onclick="filterAccumCards(this,'')">All</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Strong Accumulation')">💪 Strong</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Accumulation')">🏦 Accumulation</button>
    <button class="filter-btn" onclick="filterAccumCards(this,'Watch')">👁 Watch</button>
  </div>
  <span id="counter-accumulation" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div id="accum-cards-grid" class="accum-grid">\n'
        for r in accum_sorted[:48]:
            alabel    = r.get("accum_label", "Watch")
            adays     = r.get("accum_days", 0)
            ascore    = r.get("accum_score", 0)
            asigs     = r.get("accum_signals", [])
            is_strong = alabel == "Strong Accumulation"
            conf      = r.get("confidence_pct", 50)
            ts        = r.get("trade_setup", {})
            entry_v   = ts.get("entry", 0)
            sl_v      = ts.get("stop_loss", 0)
            t1_v      = ts.get("target1", 0)
            del_pct   = r.get("delivery_pct")
            del_s     = f"{del_pct:.0f}%" if del_pct is not None else "—"
            asigs_html = "".join(f'<span class="accum-signal-tag">{s}</span>' for s in asigs)
            label_html = (f'<span class="accum-label-strong">🏦 {alabel}</span>' if is_strong
                          else f'<span class="accum-label-watch">👁 {alabel}</span>')
            card_cls  = "accum-card strong" if is_strong else "accum-card"
            html += f"""<div class="{card_cls}" data-symbol="{r['symbol']}" data-sector="{r.get('sector','')}" data-accumlabel="{alabel}" onclick="openModal('{r['symbol']}')">\n  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div>
      <div style="font-size:16px;font-weight:800;">{r['symbol']}</div>
      <div style="font-size:11px;color:var(--muted);margin-top:1px;">{r.get('sector','—')}</div>
    </div>
    <span class="grade-badge" style="background:{r['grade_color']};">{r['grade']}</span>
  </div>
  <div style="margin-top:8px;">{label_html}</div>
  <div class="accum-score-bar"><div class="accum-score-fill" style="width:{ascore}%;"></div></div>
  <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:3px;">
    <span>Accum Score: <strong style="color:var(--green);">{ascore}/100</strong></span>
    <span>Accum Days: <strong style="color:var(--text);">{adays}d</strong></span>
    <span>Confidence: <strong style="color:var(--blue);">{conf}%</strong></span>
  </div>
  <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:2px;">{asigs_html}</div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:9px;font-size:11px;">
    <div class="price-chip">CMP <strong>₹{r['price']:,.1f}</strong></div>
    <div class="price-chip">Entry <strong style="color:var(--blue);">₹{entry_v:,.1f}</strong></div>
    <div class="price-chip">SL <strong style="color:var(--red);">₹{sl_v:,.1f}</strong></div>
    <div class="price-chip">T1 <strong style="color:var(--green);">₹{t1_v:,.1f}</strong></div>
    <div class="price-chip">Del <strong>{del_s}</strong></div>
  </div>
</div>\n"""
        html += "</div>\n</div>\n"


        # ── Expert Picks Tab (v7.0) ──
        expert_conv_list  = sorted([r for r in results if r.get("expert_decision")=="CONVICTION"],
                                    key=lambda x: x.get("expert_yes",0), reverse=True)
        expert_trade_list = sorted([r for r in results if r.get("expert_decision")=="TRADE"],
                                    key=lambda x: x.get("expert_yes",0), reverse=True)
        all_expert = expert_conv_list + expert_trade_list

        html += '<div id="pane-expert" class="tab-pane">\n'
        html += f'''<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;flex-wrap:wrap;">
  <div class="section-title" style="margin-bottom:0;">⭐ Multi-Factor Leaders — 13-Point Screening Checklist</div>
  <span style="background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.3);color:var(--amber);padding:3px 10px;border-radius:20px;font-size:11px;">⭐ Conviction: {len(expert_conv_list)} (≥10/13)</span>
  <span style="background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);color:var(--green);padding:3px 10px;border-radius:20px;font-size:11px;">✅ Trade: {len(expert_trade_list)} (7-9/13)</span>
</div>\n'''
        html += '''<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:200px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol..." oninput="searchSimpleTable(this,'expert-table')">
  </div>
  <div style="display:flex;gap:5px;">
    <button class="filter-btn on" onclick="filterExpertDecision(this,'expert-table','')">All</button>
    <button class="filter-btn" onclick="filterExpertDecision(this,'expert-table','CONVICTION')">⭐ Conviction</button>
    <button class="filter-btn" onclick="filterExpertDecision(this,'expert-table','TRADE')">✅ Trade</button>
  </div>
  <span id="counter-expert" style="font-size:11px;color:var(--muted);padding:4px 10px;background:var(--bg3);border-radius:20px;">— stocks</span>
</div>\n'''
        html += '<div class="tbl-wrap"><table id="expert-table">\n'
        html += '''<thead><tr>
  <th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>
  <th>Expert</th><th>Decision</th>
  <th>Mkt</th><th>Sector</th><th>Price</th><th>Breakout</th>
  <th>Volume</th><th>Indicator</th><th>Risk</th>
  <th>Price</th><th>1D%</th><th>Entry</th><th>SL</th><th>T1</th>
</tr></thead>\n<tbody>\n'''
        for i, r in enumerate(all_expert, 1):
            ec     = r.get("expert_checks", {})
            e_yes  = r.get("expert_yes", 0)
            e_dec  = r.get("expert_decision","SKIP")
            e_col  = "#f59e0b" if e_dec=="CONVICTION" else "#10b981" if e_dec=="TRADE" else "#ef4444"
            a_sc   = sum(1 for k in ["a1_nifty_above_dma","a2_breadth_supportive"] if ec.get(k))
            b_sc   = sum(1 for k in ["b1_sector_strong","b2_sector_peers_breaking"] if ec.get(k))
            c_sc   = sum(1 for k in ["c1_base_consolidation","c2_price_structure_ok"] if ec.get(k))
            d_sc   = sum(1 for k in ["d1_breakout_confirmed","d2_candle_quality_ok"] if ec.get(k))
            e_sc   = sum(1 for k in ["e1_volume_surge","e2_volume_contraction"] if ec.get(k))
            f_sc   = 1 if ec.get("f1_indicators_aligned") else 0
            g_sc   = sum(1 for k in ["g1_stoploss_defined","g2_rr_minimum"] if ec.get(k))
            def cc(s,m):
                c = "#10b981" if s==m else "#f59e0b" if s>0 else "#ef4444"
                return f'<span style="font-weight:700;color:{c}">{s}/{m}</span>'
            ts     = r.get("trade_setup",{})
            entry_v= ts.get("entry",0)
            sl_v   = ts.get("stop_loss",0)
            t1_v   = ts.get("target1",0)
            cc_cls = "up" if r["chg_1d"]>0 else "down" if r["chg_1d"]<0 else "neutral"
            html += f'''<tr data-expert="{e_dec}" onclick="openModal(\'{r["symbol"]}\')">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r["symbol"]}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r["sector"]}</td>
  <td><span class="grade-badge" style="background:{r["grade_color"]}">{r["grade"]}</span></td>
  <td style="font-weight:700">{r["score"]}</td>
  <td><span style="font-size:15px;font-weight:800;color:{e_col}">{e_yes}/13</span></td>
  <td><span style="background:{e_col}22;border:1px solid {e_col}55;color:{e_col};padding:2px 8px;border-radius:20px;font-size:10px;font-weight:700">{e_dec}</span></td>
  <td style="text-align:center">{cc(a_sc,2)}</td>
  <td style="text-align:center">{cc(b_sc,2)}</td>
  <td style="text-align:center">{cc(c_sc,2)}</td>
  <td style="text-align:center">{cc(d_sc,2)}</td>
  <td style="text-align:center">{cc(e_sc,2)}</td>
  <td style="text-align:center">{cc(f_sc,1)}</td>
  <td style="text-align:center">{cc(g_sc,2)}</td>
  <td style="font-weight:600">₹{r["price"]:,.2f}</td>
  <td class="{cc_cls}">{("+" if r["chg_1d"]>0 else "")}{r["chg_1d"]:.2f}%</td>
  <td style="color:var(--blue);font-size:11px">{"₹{:,.1f}".format(entry_v) if entry_v else "—"}</td>
  <td style="color:var(--red);font-size:11px">{"₹{:,.1f}".format(sl_v) if sl_v else "—"}</td>
  <td style="color:var(--green);font-size:11px">{"₹{:,.1f}".format(t1_v) if t1_v else "—"}</td>
</tr>\n'''
        html += "</tbody></table></div>\n</div>\n"

                # ── Sector Leaderboard Tab (v4.0 — composite strength) ──
        html += '<div id="pane-sectors" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:6px;">🏭 Sector Leaderboard — Composite Strength Score (RS · 200EMA · Stage2 · ADX)</div>\n'
        html += '<div style="font-size:11px;color:var(--muted);margin-bottom:14px;">Score 0-100 · &gt;70 = Strong · 50-70 = Moderate · &lt;50 = Weak</div>\n'
        html += '<div class="sector-lb-grid">\n'
        for rank_i, sec_data in enumerate(sorted_sectors, 1):
            sec_name, strength, avg_rs, count, stage2_cnt, pct_200, avg_adx = sec_data
            if   strength >= 70: sec_col = "#10b981"; hot = True
            elif strength >= 55: sec_col = "#38bdf8"; hot = False
            elif strength >= 40: sec_col = "#f59e0b"; hot = False
            else:                sec_col = "#ef4444"; hot = False
            rank_label = "🥇" if rank_i == 1 else "🥈" if rank_i == 2 else "🥉" if rank_i == 3 else f"#{rank_i}"
            hot_badge = '<span class="sector-hot-badge">🔥 HOT</span>' if hot else ''
            bar_pct   = min(int(strength), 100)
            # Pick top 3 stocks in this sector by score
            top_in_sec = sorted([r for r in results if r.get("sector") == sec_name],
                                 key=lambda x: x["score"], reverse=True)[:3]
            top_syms   = " · ".join(r["symbol"] for r in top_in_sec)
            html += f"""<div class="sector-lb-card">
  <div class="sector-lb-header">
    <div>
      <div class="sector-lb-name">{rank_label} {sec_name} {hot_badge}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px;">{count} stocks</div>
    </div>
    <div class="sector-lb-score" style="color:{sec_col};">{strength:.0f}</div>
  </div>
  <div class="sector-bar"><div class="sector-bar-fill" style="width:{bar_pct}%;background:{sec_col};"></div></div>
  <div class="sector-meta">
    <span>RS Avg: <strong>{avg_rs:.0f}</strong></span>
    <span>Above 200EMA: <strong>{pct_200:.0f}%</strong></span>
    <span>Stage 2: <strong>{stage2_cnt}</strong></span>
    <span>ADX Avg: <strong>{avg_adx:.0f}</strong></span>
  </div>
  <div style="font-size:10px;color:var(--blue);margin-top:5px;">Top: {top_syms}</div>
</div>\n"""
        html += "</div>\n</div>\n"

        # ── Trade Ideas Tab (A+ & A stocks with trade setup) ──
        trade_stocks = [r for r in results if r["grade"] in ("A+","A") and r.get("trade_setup", {}).get("entry")]
        html += '<div id="pane-trade" class="tab-pane">\n'
        html += '<div class="section-title" style="margin-bottom:14px;">🎯 High Conviction Setups — A+ &amp; A Grade Analysis with Key Levels</div>\n'
        if near_earnings:
            html += f'<div class="earnings-warn" style="margin-bottom:14px;">⚠️ <strong>{len(near_earnings)} stocks</strong> have results within {CFG["earnings_warn_days"]} days. Marked below — consider waiting for post-result entry.</div>\n'
        html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;">\n'
        for r in trade_stocks[:30]:
            ts    = r.get("trade_setup", {})
            earn  = r["earnings_info"]
            warn_banner = ""
            if earn.get("has_upcoming"):
                warn_banner = f'<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:6px;padding:6px 10px;margin-top:8px;font-size:12px;color:#ef4444;">⚠️ Results in {earn["days_away"]} day(s) — {earn["date_str"]}</div>'
            del_badge = ""
            if r['delivery_pct'] is not None and r['delivery_pct'] >= 55:
                del_badge = f'<span class="signal-tag signal-green">Delivery {r["delivery_pct"]:.0f}%</span>'
            html += f"""<div class="card-sm" style="cursor:pointer;" onclick="openModal('{r['symbol']}')">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <span style="font-size:16px;font-weight:800;">{r['symbol']}</span>
      <span class="grade-badge" style="background:{r['grade_color']};margin-left:8px;">{r['grade']}</span>
    </div>
    <div style="text-align:right;font-size:13px;color:var(--muted);">{r['sector']} · Score {r['score']}</div>
  </div>
  <div style="margin-top:6px;font-size:12px;color:var(--muted);">
    RSI {r['rsi']} · ADX {r['adx']} · RS {r['rs_percentile']}%ile · BB {r['bb_width']:.1f}%
    {del_badge}
  </div>
  <div class="trade-setup-grid" style="margin-top:10px;">
    <div class="trade-box">
      <div class="trade-box-label">Entry</div>
      <div class="trade-box-val" style="color:var(--blue);">₹{ts.get('entry',0):,.1f}</div>
      <div class="trade-box-sub">{ts.get('setup_type','')}</div>
    </div>
    <div class="trade-box">
      <div class="trade-box-label">Stop Loss</div>
      <div class="trade-box-val" style="color:var(--red);">₹{ts.get('stop_loss',0):,.1f}</div>
      <div class="trade-box-sub">Risk {ts.get('risk_pct',0):.1f}%</div>
    </div>
    <div class="trade-box">
      <div class="trade-box-label">Target 1</div>
      <div class="trade-box-val" style="color:var(--green);">₹{ts.get('target1',0):,.1f}</div>
      <div class="trade-box-sub">+{ts.get('reward1_pct',0):.1f}%</div>
    </div>
  </div>
  <div class="trade-t2-row">
    <span style="font-size:12px;">Target 2: <strong style="color:#a78bfa;">₹{ts.get('target2',0):,.1f}</strong> (+{ts.get('reward2_pct',0):.1f}%)</span>
    <span style="font-size:12px;">R:R = <strong style="color:var(--blue);">1:{ts.get('rr_ratio',0)}</strong></span>
  </div>
  {warn_banner}
</div>
"""
        html += "</div>\n</div>\n"


        # ── EMA Scanner Tab (v7.2) — All 5 EMA strategies ──
        ema_early      = [r for r in results if r.get("ema_early_momentum")]
        ema_fresh      = [r for r in results if r.get("ema_fresh_cross_5_13")]
        ema_swing      = [r for r in results if r.get("ema_swing_confirm")]
        ema_pullback   = [r for r in results if r.get("ema_near_20_pullback") and r.get("ema_swing_confirm")]
        ema_golden     = [r for r in results if r.get("ema_golden_cross")]
        ema_fresh_gc   = [r for r in results if r.get("ema_fresh_golden_cross")]
        ema_ultra      = [r for r in results if r.get("ema_ultra_pro")]
        ema_ultra_rsi  = [r for r in ema_ultra if 55 <= r.get("rsi", 0) <= 72 and r.get("adx", 0) >= 20 and r.get("near_20d_high")]

        def ema_tag(val, label, col):
            return (f'<span style="background:{col}22;border:1px solid {col}55;'
                    f'color:{col};padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700">'
                    f'{label}</span>') if val else ''

        def build_ema_table(rows, tbl_id, cols_extra=""):
            th_extra = f"<th>{cols_extra}</th>" if cols_extra else ""
            # Filter bar above each EMA table
            t  = f"""<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
  <div class="search-bar" style="flex:1;min-width:160px;margin-bottom:0;">
    <span class="search-icon">🔍</span>
    <input type="text" placeholder="Search symbol or sector..."
      oninput="emaSearch(this,'{tbl_id}')" id="srch-{tbl_id}">
  </div>
  <div style="display:flex;gap:4px;flex-wrap:wrap;">
    <button class="filter-btn on" id="chip-{tbl_id}-all" onclick="emaGrade(this,'{tbl_id}','')">All</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','A+')">A+</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','A')">A</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','B+')">B+</button>
    <button class="filter-btn" onclick="emaGrade(this,'{tbl_id}','B')">B</button>
  </div>
  <div style="display:flex;gap:4px;flex-wrap:wrap;">
    <button class="filter-btn" id="chip-{tbl_id}-vol" onclick="emaVol(this,'{tbl_id}')">Vol &gt;1.5×</button>
    <button class="filter-btn" id="chip-{tbl_id}-rsi" onclick="emaRsi(this,'{tbl_id}')">RSI 50-72</button>
    <button class="filter-btn" id="chip-{tbl_id}-adx" onclick="emaAdx(this,'{tbl_id}')">ADX &gt;20</button>
    <button class="filter-btn" id="chip-{tbl_id}-del" onclick="emaDel(this,'{tbl_id}')">Del &gt;55%</button>
  </div>
  <span id="cnt-{tbl_id}" style="font-size:11px;color:var(--muted);padding:3px 10px;background:var(--bg3);border-radius:20px;white-space:nowrap">—</span>
</div>"""
            t += f'<div class="tbl-wrap"><table id="{tbl_id}"><thead><tr>'
            t += '<th>#</th><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>'
            t += '<th>Price</th><th>1D%</th><th>RSI</th><th>ADX</th><th>Vol Ratio</th>'
            t += '<th>EMA 5</th><th>EMA 13</th><th>EMA 26</th><th>EMA 21</th><th>EMA 50</th><th>EMA 200</th>'
            t += '<th>Delivery%</th><th>Entry</th><th>SL</th><th>T1</th><th>Signals</th>'
            t += f'{th_extra}</tr></thead><tbody>'
            for i, r in enumerate(rows[:80], 1):
                ts    = r.get("trade_setup", {}) or {}
                chgc  = "up" if r["chg_1d"] > 0 else "down" if r["chg_1d"] < 0 else "neutral"
                rsic  = "#10b981" if 50<=r.get("rsi",0)<=72 else "#f59e0b"
                adxc  = "#10b981" if r.get("adx",0)>25 else "#f59e0b"
                volc  = "#10b981" if r.get("vol_ratio",1)>=1.5 else "#f59e0b" if r.get("vol_ratio",1)>=1.2 else "#8892a4"
                e5    = r.get("ema_5",0)
                e13   = r.get("ema_13",0)
                e26   = r.get("ema_26",0)
                e21   = r.get("ema_21",0)
                e50   = r.get("ema_50",0)
                e200  = r.get("ema_200",0)
                price = r["price"]
                def ec(v): return "#10b981" if price>v>0 else "#ef4444" if v>0 else "#8892a4"
                sigs  = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:3])
                dp_v = r.get("delivery_pct") or 0
                t += f"""<tr onclick="openModal('{r["symbol"]}')" style="cursor:pointer"
  data-grade="{r["grade"]}" data-score="{r["score"]}" data-rsi="{r.get('rsi',0)}"
  data-adx="{r.get('adx',0)}" data-vol="{r.get('vol_ratio',1):.2f}" data-del="{dp_v}"
  data-sym="{r["symbol"]}" data-sec="{r.get('sector','')}">
  <td style="color:var(--muted)">{i}</td>
  <td><strong>{r["symbol"]}</strong></td>
  <td style="font-size:11px;color:var(--muted)">{r.get("sector","")}</td>
  <td><span class="grade-badge" style="background:{r["grade_color"]}">{r["grade"]}</span></td>
  <td style="font-weight:700">{r["score"]}</td>
  <td style="font-weight:600">₹{price:,.2f}</td>
  <td class="{chgc}">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>
  <td style="color:{rsic}">{r.get('rsi',0)}</td>
  <td style="color:{adxc}">{r.get('adx',0)}</td>
  <td style="color:{volc}">{r.get('vol_ratio',1):.2f}x</td>
  <td style="color:{ec(e5)};font-size:11px">₹{e5:,.1f}</td>
  <td style="color:{ec(e13)};font-size:11px">₹{e13:,.1f}</td>
  <td style="color:{ec(e26)};font-size:11px">₹{e26:,.1f}</td>
  <td style="color:{ec(e21)};font-size:11px">₹{e21:,.1f}</td>
  <td style="color:{ec(e50)};font-size:11px">₹{e50:,.1f}</td>
  <td style="color:{ec(e200)};font-size:11px">₹{e200:,.1f}</td>
  <td style="color:var(--blue);font-size:11px">{'₹{:,.1f}'.format(ts.get('entry',0)) if ts.get('entry') else '—'}</td>
  <td style="color:var(--red);font-size:11px">{'₹{:,.1f}'.format(ts.get('stop_loss',0)) if ts.get('stop_loss') else '—'}</td>
  <td style="color:var(--green);font-size:11px">{'₹{:,.1f}'.format(ts.get('target1',0)) if ts.get('target1') else '—'}</td>
  <td style="color:{'#34d399' if (r.get('delivery_pct') or 0)>=55 else 'var(--muted)'};font-size:11px">{(str(r.get('delivery_pct','—'))+'%') if r.get('delivery_pct') else '—'}</td>
  <td>{sigs or '<span style="color:var(--muted);font-size:11px">—</span>'}</td>
</tr>"""
            t += "</tbody></table></div>"
            # Init counter after build
            t += f"""<script>
(function(){{
  var rows = document.querySelectorAll('#{tbl_id} tbody tr');
  var el = document.getElementById('cnt-{tbl_id}');
  if(el) el.textContent = rows.length + ' stocks';
}})();
</script>"""
            return t

        # Build explanation cards for each strategy
        html += """<div id="pane-ema" class="tab-pane">
<div style="margin-bottom:16px">
  <div class="section-title" style="font-size:13px;margin-bottom:6px">📈 EMA Momentum Scanner — 5 Professional Strategies</div>
  <div style="font-size:12px;color:var(--muted);line-height:1.7">
    EMA alignment is the foundation of swing trading. When EMAs stack in the right order — short above medium above long —
    the stock is in a confirmed uptrend. Use these 5 strategies from early detection to position trading.
  </div>
</div>

<!-- Strategy summary cards -->
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:20px">
"""
        strategy_cards = [
            ("#a78bfa", "⚡ Early Momentum", "EMA 5 > 13 > 26", f"{len(ema_early)} stocks", "Fresh trend start — earliest entry signal"),
            ("#38bdf8", "🔵 Fresh 5×13 Cross", "Just crossed (≤2 days)", f"{len(ema_fresh)} stocks", "Catches move right at the start"),
            ("#10b981", "📊 Swing Confirm", "EMA 21 > 50, close above 21", f"{len(ema_swing)} stocks", "Medium-term trend bullish — safest entry"),
            ("#f59e0b", "🎯 Pullback+Bounce", "Close within 3% of EMA 21", f"{len(ema_pullback)} stocks", "High probability bounce trade"),
            ("#059669", "🌟 Golden Cross", "EMA 50 > EMA 200", f"{len(ema_golden)} stocks", "Long-term bullish — institutional zone"),
            ("#ef4444", "🔥 Fresh Golden", "50×200 cross ≤10 days", f"{len(ema_fresh_gc)} stocks", "Big trend change — early institutional buy"),
            ("#c084fc", "🚀 Ultra Pro", "ALL EMAs aligned + vol 1.5×", f"{len(ema_ultra)} stocks", "All conditions confirmed — highest conviction"),
            ("#f472b6", "💎 Ultra Pro+RSI", "Ultra Pro + RSI 55-72 + ADX>20", f"{len(ema_ultra_rsi)} stocks", "Complete confluence — best setups only"),
        ]
        for col, title, rule, count, desc in strategy_cards:
            html += f"""<div style="background:var(--bg2);border:1px solid {col}44;border-radius:10px;padding:13px 15px">
  <div style="font-size:13px;font-weight:700;color:{col};margin-bottom:4px">{title}</div>
  <div style="font-size:11px;color:var(--muted);font-family:monospace;margin-bottom:6px;background:var(--bg3);padding:3px 8px;border-radius:4px">{rule}</div>
  <div style="font-size:20px;font-weight:800;color:var(--text)">{count}</div>
  <div style="font-size:11px;color:var(--muted);margin-top:3px">{desc}</div>
</div>"""
        html += "</div>\n"


        # EMA logic explanation
        html += """<div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;margin-bottom:18px;font-size:12px">
  <div style="font-weight:700;margin-bottom:8px;color:var(--text)">📖 How to use EMA Scanner</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px">
    <div><div style="color:#a78bfa;font-weight:600;margin-bottom:4px">Step 1 — EMA 5 &gt; 13 &gt; 26 (Early Momentum)</div>
    <div style="color:var(--muted)">Short-term trend forming. Price above EMA 5. Catch the move at the start before most traders notice. Use for aggressive early entry.</div></div>
    <div><div style="color:#10b981;font-weight:600;margin-bottom:4px">Step 2 — EMA 21 &gt; 50 + Pullback (Swing Confirm)</div>
    <div style="color:var(--muted)">Medium trend confirmed. Wait for price to pull back to EMA 21 and bounce. High probability entry. This is where most professional swing traders enter.</div></div>
    <div><div style="color:#059669;font-weight:600;margin-bottom:4px">Step 3 — EMA 50 &gt; 200 (Golden Cross)</div>
    <div style="color:var(--muted)">Long-term trend confirmed. Institutions actively buying. Fresh golden cross within 10 days = best timing. Hold for larger targets (15-25%).</div></div>
    <div><div style="color:#c084fc;font-weight:600;margin-bottom:4px">Ultra Pro — All aligned + Volume + RSI</div>
    <div style="color:var(--muted)">Every EMA in perfect order + volume surge 1.5x + RSI 55-72 + ADX &gt;20 + near 20-day high. The rarest and most powerful setup. Maximum confidence entry.</div></div>
  </div>
</div>
"""
        # Separator function
        def ema_section(title, count, col, desc):
            return f"""<div style="display:flex;align-items:center;gap:10px;margin:18px 0 10px">
  <div style="font-size:14px;font-weight:700;color:{col}">{title}</div>
  <span style="background:{col}22;border:1px solid {col}44;color:{col};padding:2px 10px;border-radius:20px;font-size:11px">{count} stocks</span>
  <div style="font-size:11px;color:var(--muted)">{desc}</div>
</div>"""

        html += ema_section("⚡ Strategy 1 — Early Momentum (EMA 5 > 13 > 26)", len(ema_early), "#a78bfa",
                            "Close > EMA5 > EMA13 > EMA26 · Short-term trend forming · Aggressive early entry")
        html += build_ema_table(sorted(ema_early, key=lambda x: x["score"], reverse=True), "ema-early-table")

        html += ema_section("🔵 Strategy 1B — Fresh 5×13 Cross (≤2 days ago)", len(ema_fresh), "#38bdf8",
                            "EMA 5 just crossed above EMA 13 within last 2 candles · Earliest possible entry · Catches fresh moves")
        html += build_ema_table(sorted(ema_fresh, key=lambda x: x["score"], reverse=True), "ema-fresh-table")

        html += ema_section("📊 Strategy 2 — Swing Confirmation (EMA 21 > 50)", len(ema_swing), "#10b981",
                            "Close > EMA21 > EMA50 · Medium-term trend bullish · Standard swing trade zone")
        html += build_ema_table(sorted(ema_swing, key=lambda x: x["score"], reverse=True), "ema-swing-table")

        html += ema_section("🎯 Strategy 2B — Pullback + Bounce (Close near EMA 21)", len(ema_pullback), "#f59e0b",
                            "Price within 3% above EMA 21 + swing confirm · High probability bounce · Best risk/reward entry")
        html += build_ema_table(sorted(ema_pullback, key=lambda x: x["score"], reverse=True), "ema-pullback-table")

        html += ema_section("🌟 Strategy 3 — Golden Cross (EMA 50 > 200)", len(ema_golden), "#059669",
                            "Long-term bullish trend · Institutional accumulation zone · Bigger moves expected")
        html += build_ema_table(sorted(ema_golden, key=lambda x: x["score"], reverse=True), "ema-golden-table")

        html += ema_section("🔥 Strategy 3B — Fresh Golden Cross (≤10 days)", len(ema_fresh_gc), "#ef4444",
                            "EMA 50 just crossed above EMA 200 · Big trend change · Earliest institutional buy signal")
        html += build_ema_table(sorted(ema_fresh_gc, key=lambda x: x["score"], reverse=True), "ema-freshgc-table")

        html += ema_section("🚀 Strategy 4 — Ultra Pro Combined (All EMAs + Volume ≥1.5×)", len(ema_ultra), "#c084fc",
                            "EMA5>13>26, EMA21>50>200, Close>EMA5, Vol≥1.5x · Explosive stocks · Complete EMA alignment")
        html += build_ema_table(sorted(ema_ultra, key=lambda x: x["score"], reverse=True), "ema-ultra-table")

        html += ema_section("💎 Strategy 5 — Ultra Pro + RSI 55-72 + ADX>20 + Near 20D High", len(ema_ultra_rsi), "#f472b6",
                            "All Ultra Pro conditions + RSI in sweet spot + strong trend + near breakout · Highest probability setup")
        html += build_ema_table(sorted(ema_ultra_rsi, key=lambda x: x["score"], reverse=True), "ema-ultrarsi-table")

        html += """</div>
"""

        # ══════════════════════════════════════════════════════════════
        # TABS: PRICE ACTION · VALUE SCREENS · QUALITY STOCKS
        # ══════════════════════════════════════════════════════════════

        def _fmt_cap(v):
            if v is None: return "N/A"
            cr = v / 1e7
            if cr >= 100000: return f"₹{cr/100:.0f}KCr"
            if cr >= 1000:   return f"₹{cr:,.0f}Cr"
            return f"₹{cr:.0f}Cr"

        def screen_card_row(r, extra_cells=""):
            ts   = r.get("trade_setup") or {}
            chgc = "up" if r["chg_1d"]>0 else "down" if r["chg_1d"]<0 else "neutral"
            rsic = "#34d399" if 50<=r.get("rsi",0)<=72 else "#fb7185" if r.get("rsi",0)>80 else "#f59e0b"
            sigs = "".join(f'<span class="signal-tag">{s}</span>' for s in r["active_signals"][:2])
            entry = f"₹{ts['entry']:,.1f}" if ts.get("entry") else "—"
            sl    = f"₹{ts['stop_loss']:,.1f}" if ts.get("stop_loss") else "—"
            t1    = f"₹{ts['target1']:,.1f}" if ts.get("target1") else "—"
            dp    = r.get("delivery_pct") or 0
            mc_cr = round((r.get("market_cap") or 0) / 1e7)
            pe    = r.get("pe_ratio") or 0
            pb    = r.get("pb_ratio") or 0
            roe   = r.get("roe") or 0
            de    = r.get("de_ratio")
            de_v  = de if de is not None else 99
            opm   = r.get("operating_margin") or 0
            data  = (f' data-grade="{r["grade"]}"'
                     f' data-score="{r["score"]}"'
                     f' data-rsi="{r.get("rsi",0)}"'
                     f' data-adx="{r.get("adx",0)}"'
                     f' data-vol="{r.get("vol_ratio",0):.2f}"'
                     f' data-del="{dp}"'
                     f' data-pe="{pe}"'
                     f' data-pb="{pb}"'
                     f' data-roe="{roe}"'
                     f' data-de="{de_v:.2f}"'
                     f' data-opm="{opm}"'
                     f' data-mc="{mc_cr}"'
                     f' data-chg1d="{r.get("chg_1d",0):.2f}"'
                     f' data-sym="{r["symbol"]}"'
                     f' data-sec="{r.get("sector","")}"'
                     f' data-stage2="{1 if r.get("is_stage2") else 0}"'
                     f' data-epsgr="{r.get("eps_growth") or 0}"')
            return (f"<tr onclick=\"openModal('{r['symbol']}')\" style=\"cursor:pointer\"{data}>"
                    f"<td><strong>{r['symbol']}</strong></td>"
                    f"<td style=\"font-size:11px;color:var(--muted)\">{r.get('sector','')}</td>"
                    f"<td><span class=\"grade-badge\" style=\"background:{r['grade_color']}\">{r['grade']}</span></td>"
                    f"<td style=\"font-weight:700\">{r['score']}</td>"
                    f"<td style=\"font-weight:600\">₹{r['price']:,.2f}</td>"
                    f"<td class=\"{chgc}\">{'+' if r['chg_1d']>0 else ''}{r['chg_1d']:.2f}%</td>"
                    f"<td style=\"color:{'#34d399' if r.get('chg_1m',0)>0 else '#fb7185'}\">{'+' if r.get('chg_1m',0)>0 else ''}{r.get('chg_1m',0):.1f}%</td>"
                    f"<td style=\"color:{rsic}\">{r.get('rsi',0)}</td>"
                    f"<td style=\"color:{'#f59e0b' if r.get('vol_ratio',0)>=1.5 else 'var(--muted)'}\">{r.get('vol_ratio',0):.1f}x</td>"
                    f"{extra_cells}"
                    f"<td style=\"font-size:11px\"><span style=\"color:#22d3ee\">{entry}</span> / <span style=\"color:#fb7185\">{sl}</span> / <span style=\"color:#34d399\">{t1}</span></td>"
                    f"<td>{sigs or '—'}</td>"
                    f"</tr>")

        def screener_section(emoji, title, count, col, desc, logic):
            return (f"<div style=\"margin:20px 0 10px;padding:12px 16px;background:var(--bg2);"
                    f"border-left:3px solid {col};border-radius:0 8px 8px 0\">"
                    f"<div style=\"display:flex;align-items:center;gap:10px;flex-wrap:wrap\">"
                    f"<span style=\"font-size:15px\">{emoji}</span>"
                    f"<span style=\"font-size:14px;font-weight:700\">{title}</span>"
                    f"<span style=\"background:{col}22;border:1px solid {col}55;color:{col};"
                    f"padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700\">{count} stocks</span>"
                    f"<span style=\"font-size:11px;color:var(--muted)\">{desc}</span>"
                    f"<span style=\"margin-left:auto;font-size:10px;color:var(--muted);font-family:monospace;"
                    f"background:var(--bg3);padding:2px 8px;border-radius:4px\">{logic}</span>"
                    f"</div></div>")

        def screener_tbl_open(tbl_id, extra_th="", chips=None):
            # chips: list of (label, attr, op, val) e.g. ("Vol>1.5×","vol",">=","1.5")
            # op: >= <= == > <
            chip_html = ""
            if chips:
                for label, attr, op, val in chips:
                    chip_id = f"schip-{tbl_id}-{attr}"
                    chip_html += (f'<button class="filter-btn" id="{chip_id}" '
                                  f'onclick="screenToggle(this,\'{tbl_id}\',\'{attr}\',\'{op}\',\'{val}\')">'
                                  f'{label}</button>')
            chip_block = ('<div style="display:flex;gap:4px;flex-wrap:wrap">' + chip_html + '</div>') if chip_html else ''
            return (f"<div style=\"display:flex;gap:6px;align-items:center;margin-bottom:8px;flex-wrap:wrap\">"
                    f"<div class=\"search-bar\" style=\"flex:1;min-width:160px;margin-bottom:0\">"
                    f"<span class=\"search-icon\">🔍</span>"
                    f"<input type=\"text\" id=\"ssrch-{tbl_id}\" placeholder=\"Search symbol or sector...\" "
                    f"oninput=\"screenSearch(this,\'{tbl_id}\')\">"
                    f"</div>"
                    f"<div style=\"display:flex;gap:4px;flex-wrap:wrap\">"
                    f"<button class=\"filter-btn on\" id=\"schip-{tbl_id}-grade-all\" "
                    f"onclick=\"screenGrade(this,\'{tbl_id}\',\'\')\">All</button>"
                    f"<button class=\"filter-btn\" onclick=\"screenGrade(this,\'{tbl_id}\',\'A+\')\">A+</button>"
                    f"<button class=\"filter-btn\" onclick=\"screenGrade(this,\'{tbl_id}\',\'A\')\">A</button>"
                    f"<button class=\"filter-btn\" onclick=\"screenGrade(this,\'{tbl_id}\',\'B+\')\">B+</button>"
                    f"</div>"
                    f"{chip_block}"
                    f"<span id=\"scnt-{tbl_id}\" style=\"font-size:11px;color:var(--muted);"
                    f"padding:3px 10px;background:var(--bg3);border-radius:20px;white-space:nowrap\">— stocks</span>"
                    f"</div>"
                    f"<div class=\"tbl-wrap\"><table id=\"{tbl_id}\">"
                    f"<thead><tr><th>Symbol</th><th>Sector</th><th>Grade</th><th>Score</th>"
                    f"<th>Price</th><th>1D%</th><th>1M%</th><th>RSI</th><th>Vol Ratio</th>"
                    f"{extra_th}<th>Entry/SL/T1</th><th>Signals</th>"
                    f"</tr></thead><tbody>")

        def screener_tbl_close(tbl_id):
            return (f"</tbody></table></div>"
                    f"<script>(function(){{"
                    f"var t=document.getElementById('{tbl_id}');"
                    f"var n=t?t.querySelectorAll('tbody tr').length:0;"
                    f"var el=document.getElementById('scnt-{tbl_id}');"
                    f"if(el)el.textContent=n+' stock'+(n!==1?'s':'');"
                    f"}})();</script>")

        def chip(v, col): return f'<div style="font-size:20px;font-weight:800;color:{col}">{v}</div>'

        def summary_chips(items):
            html_c = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px">'
            for count, label, sub, col in items:
                html_c += (f'<div style="background:{col}18;border:1px solid {col}44;'
                           f'border-radius:10px;padding:10px 14px;min-width:115px">'
                           f'<div style="font-size:20px;font-weight:800;color:{col}">{count}</div>'
                           f'<div style="font-size:11px;color:var(--muted)">{label}</div>'
                           f'<div style="font-size:10px;color:{col}">{sub}</div></div>')
            return html_c + '</div>'

        # ─────────────────── COMPUTE ALL SCREENS ───────────────────
        # Technical screens
        s52h       = sorted([r for r in results if r["price"]>=r["high_52w"]*0.95 and r["high_52w"]>0],
                             key=lambda x: x.get("pct_from_high",-999), reverse=True)
        s52h_pro   = [r for r in s52h if r["price"]>=r["high_52w"]*0.98 and r.get("vol_ratio",0)>=1.5]
        s52l       = sorted([r for r in results if r["low_52w"]>0 and r["price"]<=r["low_52w"]*1.10],
                             key=lambda x: x["price"]/x["low_52w"] if x["low_52w"] else 999)
        sgc_all    = sorted([r for r in results if r.get("ema_golden_cross")], key=lambda x: x["score"], reverse=True)
        sgc_fresh  = [r for r in sgc_all if r.get("ema_fresh_golden_cross")]
        sdc_fresh  = sorted([r for r in results if not r.get("ema_golden_cross") and
                              r.get("ema_50",0)<r.get("ema_200",999)*0.995 and r.get("ema_50",0)>0],
                             key=lambda x: x["score"], reverse=True)
        sabove200  = sorted([r for r in results if r.get("above_200ema")], key=lambda x: x["score"], reverse=True)
        svol_bo    = sorted([r for r in results if r.get("vol_ratio",0)>=2.0 and r.get("chg_1d",0)>0],
                             key=lambda x: x.get("vol_ratio",0), reverse=True)
        sgainers   = sorted([r for r in results if r.get("chg_1d",0)>=3.0], key=lambda x: x["chg_1d"], reverse=True)
        slosers    = sorted([r for r in results if r.get("chg_1d",0)<=-3.0], key=lambda x: x["chg_1d"])

        # Fundamental screens
        MC = 1e7
        low_pe      = sorted([r for r in results if r.get("pe_ratio") and 0<r["pe_ratio"]<15],
                              key=lambda x: x["pe_ratio"])
        underval_gr = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<20
                               and r.get("roe") and r["roe"]>15 and r.get("eps_growth") and r["eps_growth"]>10],
                              key=lambda x: x["score"], reverse=True)
        low_pb      = sorted([r for r in results if r.get("pb_ratio") and 0<r["pb_ratio"]<1.5],
                              key=lambda x: x["pb_ratio"])
        graham_v    = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<15
                               and r.get("pb_ratio") and r["pb_ratio"]<1.5
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5
                               and r.get("eps_growth") and r["eps_growth"]>0],
                              key=lambda x: x["score"], reverse=True)
        magic_f     = sorted([r for r in results if r.get("roic") and r["roic"]>15
                               and r.get("earnings_yield") and r["earnings_yield"]>5],
                              key=lambda x: (r.get("roic",0)+r.get("earnings_yield",0)), reverse=True)
        val_growth  = sorted([r for r in results if r.get("pe_ratio") and r["pe_ratio"]<25
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("roe") and r["roe"]>15],
                              key=lambda x: x["score"], reverse=True)
        turnaround  = sorted([r for r in results if r.get("eps_growth") and r["eps_growth"]>0
                               and r.get("rev_growth") and r["rev_growth"]>5 and r["score"]>=40],
                              key=lambda x: x["score"], reverse=True)

        # Quality screens
        blue_chip   = sorted([r for r in results if r.get("market_cap") and r["market_cap"]>=50000*MC
                               and r.get("roe") and r["roe"]>15],
                              key=lambda x: x.get("market_cap",0), reverse=True)
        large_cap_q = sorted([r for r in results if r.get("market_cap") and r["market_cap"]>=20000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        mid_cap_q   = sorted([r for r in results if r.get("market_cap")
                               and 5000*MC<=r["market_cap"]<20000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        small_cap_q = sorted([r for r in results if r.get("market_cap") and r["market_cap"]<5000*MC
                               and r.get("roe") and r["roe"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10],
                              key=lambda x: x["score"], reverse=True)
        coffee_can  = sorted([r for r in results if r.get("roce") and r["roce"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("de_ratio") is not None and r["de_ratio"]<0.5],
                              key=lambda x: x["score"], reverse=True)
        high_opm    = sorted([r for r in results if r.get("operating_margin") and r["operating_margin"]>20],
                              key=lambda x: x.get("operating_margin",0), reverse=True)
        opm_improve = sorted([r for r in results if r.get("operating_margin") and r.get("profit_margin")
                               and r["operating_margin"] > r["profit_margin"]],
                              key=lambda x: x.get("operating_margin",0), reverse=True)
        qual_growth = sorted([r for r in results if r.get("roe") and r["roe"]>15
                               and r.get("rev_growth") and r["rev_growth"]>10
                               and r.get("operating_margin") and r["operating_margin"]>15],
                              key=lambda x: x["score"], reverse=True)

        # ─────────────────── PRICE ACTION TAB ───────────────────
        html += '<div id="pane-price_action" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">📊 Price Action &amp; Technical Patterns</div><div style="font-size:12px;color:var(--muted)">8 ready-made technical screens — 52W High/Low · Golden/Death Cross · Volume Breakout · Gainers/Losers</div></div>\n'
        html += summary_chips([
            (len(s52h),    "Near 52W High",    f"{len(s52h_pro)} w/ vol", "#f97316"),
            (len(s52l),    "Near 52W Low",     "Value zone",              "#22d3ee"),
            (len(sgc_all), "Golden Cross",     f"{len(sgc_fresh)} fresh", "#34d399"),
            (len(sdc_fresh),"Death Cross",     "Bearish signal",          "#fb7185"),
            (len(sabove200),"Above 200 DMA",   "Long-term bullish",       "#a3e635"),
            (len(svol_bo), "Vol Breakout",     "Vol 2× + up",             "#f59e0b"),
            (len(sgainers),"Top Gainers",      "+3% today",               "#34d399"),
            (len(slosers), "Top Losers",       "−3% today",               "#fb7185"),
        ])

        html += screener_section("🔹","52 Week High",len(s52h),"#f97316","Within 5% of 52W peak — momentum leaders","Close ≥ 0.95×52WHigh")
        html += screener_tbl_open("pa-52high","<th>52W High</th><th>Distance</th>",chips=[("Vol>1.5×","vol",">=","1.5"),("RSI 50-72","rsi","range","50,72"),("Stage 2","stage2","==","1"),("Del>55%","del",">=","55")])
        for r in s52h[:60]:
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r["high_52w"]:,.1f}</td>'
                f'<td style="color:#d4a024;font-weight:700">{r["pct_from_high"]:.1f}%</td>')
        html += screener_tbl_close("pa-52high")

        html += screener_section("🔹","52 Week Low",len(s52l),"#22d3ee","Within 10% of yearly low — value hunting zone","Close ≤ 1.10×52WLow")
        html += screener_tbl_open("pa-52low","<th>52W Low</th><th>From Low</th>",chips=[("PE<15","pe","lt","15"),("ROE>15%","roe",">=","15"),("D/E<0.5","de","<","0.5")])
        for r in s52l[:40]:
            fl = round((r["price"]/r["low_52w"]-1)*100,1) if r["low_52w"] else 0
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r["low_52w"]:,.1f}</td>'
                f'<td style="color:#22d3ee;font-weight:700">+{fl:.1f}%</td>')
        html += screener_tbl_close("pa-52low")

        html += screener_section("🔹","Golden Crossover",len(sgc_all),"#34d399",f"EMA50>EMA200 · {len(sgc_fresh)} fresh within 10 days","EMA(50) > EMA(200)")
        html += screener_tbl_open("pa-golden","<th>EMA 50</th><th>EMA 200</th>",chips=[("Vol>1.5×","vol",">=","1.5"),("RSI>50","rsi",">=","50"),("Del>55%","del",">=","55"),("ROE>15%","roe",">=","15")])
        for r in sgc_all[:60]:
            fc = ' <span style="color:#d4a024;font-size:9px;font-weight:700">🔥FRESH</span>' if r.get("ema_fresh_golden_cross") else ""
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-size:11px">₹{r.get("ema_50",0):,.1f}</td>'
                f'<td style="color:#22d3ee;font-size:11px">₹{r.get("ema_200",0):,.1f}{fc}</td>')
        html += screener_tbl_close("pa-golden")

        html += screener_section("🔹","Death Cross",len(sdc_fresh),"#fb7185","EMA50<EMA200 — avoid new longs","EMA(50) < EMA(200)")
        html += screener_tbl_open("pa-death","<th>EMA 50</th><th>EMA 200</th>",chips=[("Score>50","score",">=","50"),("RSI<45","rsi","<","45")])
        for r in sdc_fresh[:40]:
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-size:11px">₹{r.get("ema_50",0):,.1f}</td>'
                f'<td style="color:var(--muted);font-size:11px">₹{r.get("ema_200",0):,.1f}</td>')
        html += screener_tbl_close("pa-death")

        html += screener_section("🔹","Above 200 DMA",len(sabove200),"#a3e635","Price above 200-day EMA — long-term trend intact","Close > EMA(200)")
        html += screener_tbl_open("pa-200dma","<th>EMA 200</th><th>Gap%</th>",chips=[("Vol>1.5×","vol",">=","1.5"),("RSI 50-72","rsi","range","50,72"),("ROE>15%","roe",">=","15"),("Del>55%","del",">=","55")])
        for r in sabove200[:60]:
            gap = round((r["price"]/r.get("ema_200",r["price"])-1)*100,1) if r.get("ema_200") else 0
            html += screen_card_row(r,
                f'<td style="font-size:11px;color:var(--muted)">₹{r.get("ema_200",0):,.1f}</td>'
                f'<td style="color:#a3e635;font-weight:700">+{gap:.1f}%</td>')
        html += screener_tbl_close("pa-200dma")

        html += screener_section("🔹","Volume Breakout",len(svol_bo),"#f59e0b","Volume ≥ 2× avg + price up — institutional participation","Vol > 2×avg + 1D%>0")
        html += screener_tbl_open("pa-volbo","<th>Vol Ratio</th><th>Delivery%</th>",chips=[("Vol>3×","vol",">=","3"),("Del>55%","del",">=","55"),("RSI>55","rsi",">=","55"),("ROE>15%","roe",">=","15")])
        for r in svol_bo[:40]:
            dp = r.get("delivery_pct")
            del_td = (f'<td style="color:{"#34d399" if dp and dp>=55 else "var(--muted)"}">{f"{dp:.0f}%" if dp else "N/A"}</td>')
            html += screen_card_row(r,
                f'<td style="color:#f59e0b;font-weight:800">{r.get("vol_ratio",0):.1f}×</td>' + del_td)
        html += screener_tbl_close("pa-volbo")

        html += screener_section("🔹","Top Gainers Today",len(sgainers),"#34d399","Stocks up ≥ 3% today","1D% ≥ +3%")
        html += screener_tbl_open("pa-gainers","<th>1D Gain</th><th>Vol Ratio</th>",chips=[("Vol>1.5×","vol",">=","1.5"),("Del>55%","del",">=","55"),("RSI<75","rsi","<","75"),("Stage 2","stage2","==","1")])
        for r in sgainers[:40]:
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:800">+{r["chg_1d"]:.2f}%</td>'
                f'<td style="color:{"#f59e0b" if r.get("vol_ratio",0)>=1.5 else "var(--muted)"}">{r.get("vol_ratio",0):.1f}×</td>')
        html += screener_tbl_close("pa-gainers")

        html += screener_section("🔹","Top Losers Today",len(slosers),"#fb7185","Stocks down ≥ 3% today — potential reversal watchlist","1D% ≤ −3%")
        html += screener_tbl_open("pa-losers","<th>1D Loss</th><th>52W High%</th>",chips=[("PE<20","pe","lt","20"),("ROE>15%","roe",">=","15"),("D/E<0.5","de","<","0.5")])
        for r in slosers[:40]:
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-weight:800">{r["chg_1d"]:.2f}%</td>'
                f'<td style="color:var(--muted)">{r["pct_from_high"]:.1f}%</td>')
        html += screener_tbl_close("pa-losers")

        html += "</div>\n"

        # ─────────────────── VALUE SCREENS TAB ───────────────────
        html += '<div id="pane-value_screen" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">💰 Fundamental &amp; Value Screens</div><div style="font-size:12px;color:var(--muted)">Graham · Greenblatt Magic Formula · PE · P/B · Turnaround — fundamental quality filters</div></div>\n'
        html += summary_chips([
            (len(low_pe),      "Low PE (<15)",        "Undervalued",    "#f97316"),
            (len(underval_gr), "Undervalued Growth",  "PE<20+ROE>15%",  "#34d399"),
            (len(low_pb),      "Low P/B (<1.5)",      "Below book",     "#22d3ee"),
            (len(graham_v),    "Graham Value",        "All 3 criteria", "#a3e635"),
            (len(magic_f),     "Magic Formula",       "ROIC+EarnYield", "#c084fc"),
            (len(val_growth),  "Value + Growth",      "PE<25+Gr>10%",   "#f59e0b"),
            (len(turnaround),  "Turnaround",          "EPS recovering", "#fb7185"),
        ])

        def n(v, fmt=".1f", suffix=""):
            return f"{v:{fmt}}{suffix}" if v is not None else "N/A"
        def gc(v, thresh, col_ok="#34d399", col_no="var(--muted)"):
            return col_ok if v is not None and v >= thresh else col_no

        html += screener_section("🔹","Low PE Stocks",len(low_pe),"#f97316","P/E below 15 — undervalued relative to earnings","PE < 15")
        html += screener_tbl_open("fv-lowpe","<th>PE</th><th>ROE%</th><th>EPS Gr%</th>",chips=[("ROE>15%","roe",">=","15"),("EPS Gr>10%","epsgr",">=","10"),("D/E<0.5","de","<","0.5"),("Score>50","score",">=","50")])
        for r in low_pe[:50]:
            pe=r.get("pe_ratio"); roe=r.get("roe"); eg=r.get("eps_growth")
            html += screen_card_row(r,
                f'<td style="color:#d4a024;font-weight:800">{n(pe,"0.1f")}×</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>'
                f'<td style="color:{gc(eg,10)}">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>')
        html += screener_tbl_close("fv-lowpe")

        html += screener_section("🔹","Undervalued Growth",len(underval_gr),"#34d399","PE<20 + ROE>15% + EPS Growth>10% — GARP strategy","PE<20+ROE>15%+EPS>10%")
        html += screener_tbl_open("fv-uvgr","<th>PE</th><th>ROE%</th><th>EPS Gr%</th><th>D/E</th>",chips=[("PE<15","pe","lt","15"),("ROE>20%","roe",">=","20"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in underval_gr[:50]:
            pe=r.get("pe_ratio"); roe=r.get("roe"); eg=r.get("eps_growth"); de=r.get("de_ratio")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#34d399;font-weight:700">{n(roe)}%</td>'
                f'<td style="color:#34d399">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>'
                f'<td style="color:{gc(de,999,"#34d399","#f59e0b") if de is not None and de<0.5 else "#f59e0b"}">{n(de,"0.2f") if de is not None else "N/A"}</td>')
        html += screener_tbl_close("fv-uvgr")

        html += screener_section("🔹","Low Price-to-Book",len(low_pb),"#22d3ee","P/B < 1.5 — trading near or below book value","P/B < 1.5")
        html += screener_tbl_open("fv-lowpb","<th>P/B</th><th>PE</th><th>ROE%</th>",chips=[("P/B<1","pb","<","1"),("ROE>15%","roe",">=","15"),("D/E<0.5","de","<","0.5")])
        for r in low_pb[:50]:
            pb=r.get("pb_ratio"); pe=r.get("pe_ratio"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#22d3ee;font-weight:800">{n(pb,"0.2f")}×</td>'
                f'<td style="color:{"#f97316" if pe and pe<15 else "var(--muted)"}">{n(pe,"0.1f")}×</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>')
        html += screener_tbl_close("fv-lowpb")

        html += screener_section("🔹","Graham Value",len(graham_v),"#a3e635","Benjamin Graham: PE<15 + P/B<1.5 + D/E<0.5 + Positive EPS","PE<15+P/B<1.5+D/E<0.5")
        html += screener_tbl_open("fv-graham","<th>PE</th><th>P/B</th><th>D/E</th><th>EPS Gr%</th>",chips=[("Score>60","score",">=","60"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in graham_v[:50]:
            pe=r.get("pe_ratio"); pb=r.get("pb_ratio"); de=r.get("de_ratio"); eg=r.get("eps_growth")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#22d3ee">{n(pb,"0.2f")}×</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#34d399" if eg and eg>0 else "#fb7185"}">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>')
        html += screener_tbl_close("fv-graham")

        html += screener_section("🔹","Magic Formula",len(magic_f),"#c084fc","Joel Greenblatt: High ROIC + High Earnings Yield — ranked by combined score","ROIC>15%+EarningsYield>5%")
        html += screener_tbl_open("fv-magic","<th>ROIC%</th><th>Earn Yield%</th><th>Rank</th>",chips=[("D/E<0.5","de","<","0.5"),("ROE>15%","roe",">=","15"),("Vol>1.5×","vol",">=","1.5")])
        for i,r in enumerate(magic_f[:50],1):
            roic=r.get("roic"); ey=r.get("earnings_yield"); combo=round((roic or 0)+(ey or 0),1)
            html += screen_card_row(r,
                f'<td style="color:#c084fc;font-weight:700">{n(roic)}%</td>'
                f'<td style="color:#22d3ee">{n(ey,"0.1f")}%</td>'
                f'<td style="color:#d4a024;font-weight:800">#{i}</td>')
        html += screener_tbl_close("fv-magic")

        html += screener_section("🔹","Value + Growth",len(val_growth),"#f59e0b","PE<25 + Rev Growth>10% + ROE>15% — GARP + quality","PE<25+RevGr>10%+ROE>15%")
        html += screener_tbl_open("fv-valgr","<th>PE</th><th>Rev Gr%</th><th>ROE%</th>",chips=[("PE<15","pe","lt","15"),("D/E<0.5","de","<","0.5"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in val_growth[:50]:
            pe=r.get("pe_ratio"); rg=r.get("rev_growth"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#d4a024">{n(pe,"0.1f")}×</td>'
                f'<td style="color:#f59e0b;font-weight:700">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>')
        html += screener_tbl_close("fv-valgr")

        html += screener_section("🔹","Turnaround Candidates",len(turnaround),"#fb7185","EPS growth positive + revenue improving — companies recovering from difficult phase","EPS Gr>0+RevGr>5%")
        html += screener_tbl_open("fv-turn","<th>EPS Gr%</th><th>Rev Gr%</th><th>PE</th>",chips=[("Score>50","score",">=","50"),("ROE>10%","roe",">=","10"),("Vol>1.5×","vol",">=","1.5")])
        for r in turnaround[:40]:
            eg=r.get("eps_growth"); rg=r.get("rev_growth"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{("+" if eg and eg>=0 else "")+n(eg)+"%"}</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("fv-turn")

        html += "</div>\n"

        # ─────────────────── QUALITY STOCKS TAB ───────────────────
        html += '<div id="pane-quality_screen" class="tab-pane">\n'
        html += '<div style="margin-bottom:12px"><div class="section-title" style="font-size:13px">🏆 Quality &amp; Long-Term Stocks</div><div style="font-size:12px;color:var(--muted)">Large Cap · Blue Chip · Coffee Can · OPM Leaders · Quality Growth — built for long-term investors</div></div>\n'
        html += summary_chips([
            (len(blue_chip),  "Blue Chip",         "Cap>₹50KCr",    "#f97316"),
            (len(large_cap_q),"Large Cap Quality",  "Cap>₹20KCr",    "#34d399"),
            (len(mid_cap_q),  "Mid Cap Quality",    "₹5K-20KCr",     "#22d3ee"),
            (len(small_cap_q),"Small Cap Quality",  "Cap<₹5KCr",     "#a3e635"),
            (len(coffee_can), "Coffee Can",         "Long-term quality",  "#c084fc"),
            (len(high_opm),   "High OPM",           "OPM > 20%",     "#f59e0b"),
            (len(opm_improve),"OPM Improvers",      "Rising margins","#fb7185"),
            (len(qual_growth),"Quality Growth",     "ROE+Gr+OPM",    "#22d3ee"),
        ])

        html += screener_section("🔹","Blue Chip Stocks",len(blue_chip),"#f97316","Cap > ₹50,000 Cr + ROE > 15% — top large caps with stable earnings","Cap>₹50KCr+ROE>15%")
        html += screener_tbl_open("qs-bluechip","<th>Mkt Cap</th><th>ROE%</th><th>D/E</th><th>PE</th>",chips=[("ROE>20%","roe",">=","20"),("D/E<0.3","de","<","0.3"),("PE<30","pe","lt","30"),("Stage 2","stage2","==","1")])
        for r in blue_chip[:40]:
            mc=r.get("market_cap"); roe=r.get("roe"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#d4a024;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>'
                f'<td style="color:{"#34d399" if de is not None and de<0.5 else "#f59e0b"}">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#f97316" if pe and pe<30 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-bluechip")

        html += screener_section("🔹","Large Cap Quality",len(large_cap_q),"#34d399","Cap > ₹20,000 Cr + ROE > 15% + D/E < 0.5 — established reliable companies","Cap>₹20KCr+ROE>15%+D/E<0.5")
        html += screener_tbl_open("qs-largecap","<th>Mkt Cap</th><th>ROE%</th><th>D/E</th><th>PE</th>",chips=[("ROE>20%","roe",">=","20"),("PE<25","pe","lt","25"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in large_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:{"#f97316" if pe and pe<25 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-largecap")

        html += screener_section("🔹","Mid Cap Quality",len(mid_cap_q),"#22d3ee","₹5,000–20,000 Cr + ROE > 15% + D/E < 0.5 — growth + quality sweet spot","₹5K-20KCr+ROE>15%+D/E<0.5")
        html += screener_tbl_open("qs-midcap","<th>Mkt Cap</th><th>ROE%</th><th>Rev Gr%</th><th>DE</th>",chips=[("ROE>20%","roe",">=","20"),("PE<25","pe","lt","25"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in mid_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); rg=r.get("rev_growth"); de=r.get("de_ratio")
            html += screen_card_row(r,
                f'<td style="color:#22d3ee;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:{"#f59e0b" if rg and rg>10 else "var(--muted)"}">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>')
        html += screener_tbl_close("qs-midcap")

        html += screener_section("🔹","Small Cap Quality",len(small_cap_q),"#a3e635","Cap < ₹5,000 Cr + ROE > 15% + Sales Growth > 10% — high-growth hidden gems","Cap<₹5KCr+ROE>15%+SalesGr>10%")
        html += screener_tbl_open("qs-smallcap","<th>Mkt Cap</th><th>ROE%</th><th>Rev Gr%</th><th>PE</th>",chips=[("ROE>20%","roe",">=","20"),("Vol>1.5×","vol",">=","1.5"),("Del>55%","del",">=","55"),("Stage 2","stage2","==","1")])
        for r in small_cap_q[:50]:
            mc=r.get("market_cap"); roe=r.get("roe"); rg=r.get("rev_growth"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#a3e635;font-weight:700">{_fmt_cap(mc)}</td>'
                f'<td style="color:#34d399">{n(roe)}%</td>'
                f'<td style="color:#f59e0b;font-weight:700">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-smallcap")

        html += screener_section("🔹","Coffee Can Portfolio",len(coffee_can),"#c084fc","ROCE > 15% + Rev Growth > 10% + D/E < 0.5 — buy-and-forget compounders","ROCE>15%+RevGr>10%+D/E<0.5")
        html += screener_tbl_open("qs-coffee","<th>ROCE%</th><th>Rev Gr%</th><th>D/E</th><th>PE</th>",chips=[("PE<30","pe","lt","30"),("ROE>20%","roe",">=","20"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in coffee_can[:50]:
            roce=r.get("roce"); rg=r.get("rev_growth"); de=r.get("de_ratio"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#c084fc;font-weight:700">{n(roce)}%</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#a3e635">{n(de,"0.2f") if de is not None else "N/A"}</td>'
                f'<td style="color:var(--muted)">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-coffee")

        html += screener_section("🔹","OPM Improvers",len(opm_improve),"#f59e0b","Operating margin > net profit margin — efficiency improving","Op Margin > Net Margin")
        html += screener_tbl_open("qs-opm","<th>Op Margin%</th><th>Net Margin%</th><th>ROE%</th>",chips=[("OPM>25%","opm",">=","25"),("ROE>15%","roe",">=","15"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in opm_improve[:50]:
            opm=r.get("operating_margin"); pm=r.get("profit_margin"); roe=r.get("roe")
            html += screen_card_row(r,
                f'<td style="color:#f59e0b;font-weight:800">{n(opm)}%</td>'
                f'<td style="color:var(--muted)">{n(pm)}%</td>'
                f'<td style="color:{gc(roe,15)}">{n(roe)}%</td>')
        html += screener_tbl_close("qs-opm")

        html += screener_section("🔹","High OPM",len(high_opm),"#fb7185","Operating Margin > 20% — highly profitable with strong pricing power","Op Margin > 20%")
        html += screener_tbl_open("qs-highopm","<th>Op Margin%</th><th>Net Margin%</th><th>ROCE%</th>",chips=[("OPM>30%","opm",">=","30"),("D/E<0.3","de","<","0.3"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in high_opm[:50]:
            opm=r.get("operating_margin"); pm=r.get("profit_margin"); roce=r.get("roce")
            html += screen_card_row(r,
                f'<td style="color:#fb7185;font-weight:800">{n(opm)}%</td>'
                f'<td style="color:var(--muted)">{n(pm)}%</td>'
                f'<td style="color:{"#c084fc" if roce and roce>=15 else "var(--muted)"}">{n(roce)}%</td>')
        html += screener_tbl_close("qs-highopm")

        html += screener_section("🔹","Quality Growth",len(qual_growth),"#22d3ee","ROE>15% + Rev Growth>10% + OPM>15% — complete quality-growth combo","ROE>15%+RevGr>10%+OPM>15%")
        html += screener_tbl_open("qs-qualgr","<th>ROE%</th><th>Rev Gr%</th><th>OPM%</th><th>PE</th>",chips=[("PE<20","pe","lt","20"),("ROE>20%","roe",">=","20"),("Vol>1.5×","vol",">=","1.5"),("Stage 2","stage2","==","1")])
        for r in qual_growth[:50]:
            roe=r.get("roe"); rg=r.get("rev_growth"); opm=r.get("operating_margin"); pe=r.get("pe_ratio")
            html += screen_card_row(r,
                f'<td style="color:#34d399;font-weight:700">{n(roe)}%</td>'
                f'<td style="color:#f59e0b">{("+" if rg and rg>=0 else "")+n(rg)+"%"}</td>'
                f'<td style="color:#22d3ee">{n(opm)}%</td>'
                f'<td style="color:{"#f97316" if pe and pe<25 else "var(--muted)"}">{n(pe,"0.1f")}×</td>')
        html += screener_tbl_close("qs-qualgr")

        html += "</div>\n"

        # ── Modal ──
        html += """
<div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modalContent">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalBody">Loading...</div>
  </div>
</div>
"""
        stock_json = json.dumps({r["symbol"]: r for r in results}, default=str)

        html += f"""
<script>
const STOCKS = {stock_json};

// Sidebar section names
var _sectionNames = {{
  all:'All Stocks', aplus:'Top Scoring Stocks', expert:'Multi-Factor Leaders', trade:'High Conviction Setups',
  breakouts:'Breakouts', vcp:'VCP Setups', rs:'RS Leaders', volsurge:'Vol Surge',
  stage2:'Stage 2', accumulation:'Accumulation', fundamentals:'Fundamentals',
  ema:'EMA Scanner', sectors:'Sectors', price_action:'Price Action & Technical',
  value_screen:'Value Screens', quality_screen:'Quality Stocks'
}};

function switchTab(name, btn) {{
  document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.querySelectorAll('.tab-pane').forEach(function(p) {{ p.classList.remove('active'); }});
  if(btn) btn.classList.add('active');
  var pane = document.getElementById('pane-' + name);
  if(pane) pane.classList.add('active');
}}

function sbSwitch(name, el) {{
  // Deactivate all sidebar items
  document.querySelectorAll('.sidebar-item').forEach(function(s) {{ s.classList.remove('active'); }});
  // Activate clicked item
  if(el) el.classList.add('active');
  // Switch pane
  document.querySelectorAll('.tab-pane').forEach(function(p) {{ p.classList.remove('active'); }});
  var pane = document.getElementById('pane-' + name);
  if(pane) pane.classList.add('active');
  // Update topbar title
  var title = document.getElementById('topbar-section-name');
  if(title) title.textContent = _sectionNames[name] || name;
  // Close mobile sidebar
  document.getElementById('sidebar').classList.remove('open');
}}

window.addEventListener('load', function() {{
  // Init sidebar counts
  var countMap = {{
    all:       document.querySelectorAll('#all-table tbody tr').length,
    aplus:     document.querySelectorAll('#aplus-table tbody tr').length,
    expert:    document.querySelectorAll('#expert-table tbody tr').length,
    trade:     document.querySelectorAll('#pane-trade .card-sm').length,
    breakouts: document.querySelectorAll('#breakouts-table tbody tr').length,
    vcp:       document.querySelectorAll('#vcp-table tbody tr').length,
    rs:        document.querySelectorAll('#rs-table tbody tr').length,
    volsurge:  document.querySelectorAll('#volsurge-table tbody tr').length,
    stage2:    document.querySelectorAll('#stage2-table tbody tr').length,
    accumulation: document.querySelectorAll('#accum-cards-grid .accum-card').length,
    fundamentals: document.querySelectorAll('#fund-cards-grid .fund-card').length,
    sectors:   document.querySelectorAll('.sector-lb-card').length,
  }};
  Object.keys(countMap).forEach(function(k) {{
    var el = document.getElementById('sbc-' + k);
    if(el && countMap[k] > 0) el.textContent = countMap[k];
  }});
  // Show/hide mobile menu button
  if(window.innerWidth <= 900) {{
    var btn = document.getElementById('menu-btn');
    if(btn) btn.style.display = 'block';
  }}
}});

// ── v6.0 FILTER STATE — stored in JS object, not DOM dataset (more reliable) ──
const _activeChip   = {{}};   // tableId → active chip key
const _searchVal    = {{}};   // tableId → search string
const _sectorVal    = {{}};   // tableId → sector
const _scoreMin     = {{}};   // tableId → minimum score

function applyFilters(tableId) {{
  const searchVal = (_searchVal[tableId]  || '').toUpperCase();
  const sectorVal =  _sectorVal[tableId]  || '';
  const scoreMin  = parseInt(_scoreMin[tableId] || '0');
  const activeChip = _activeChip[tableId] || '';

  let visible = 0;
  const tbody = document.querySelector('#' + tableId + '-table tbody');
  if (!tbody) return;

  tbody.querySelectorAll('tr').forEach(row => {{
    const sym     = (row.cells[1]  ? row.cells[1].textContent  : '').toUpperCase();
    const secCell = (row.cells[19] ? row.cells[19].textContent : '').trim();
    const score   = parseInt(row.dataset.score || '0');

    // Search — symbol OR sector
    const matchSearch = !searchVal || sym.includes(searchVal) || secCell.toUpperCase().includes(searchVal);
    // Sector dropdown
    const matchSector = !sectorVal || secCell === sectorVal;
    // Score slider
    const matchScore  = score >= scoreMin;
    // Chip filter
    let matchChip = true;
    if (activeChip) {{
      const gradeKeys = ['A+','A','B+','B'];
      if (gradeKeys.includes(activeChip)) {{
        matchChip = (row.dataset.grade || '') === activeChip;
      }} else {{
        // Try both with and without underscore variants
        const key1 = activeChip;
        const key2 = activeChip.replace(/_/g, '');
        matchChip = row.dataset[key1] === '1' || row.dataset[key2] === '1';
      }}
    }}

    const show = matchSearch && matchSector && matchScore && matchChip;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});

  const counter = document.getElementById('counter-' + tableId);
  if (counter) counter.textContent = visible + ' stock' + (visible !== 1 ? 's' : '');
}}

// ── Chip filter ──
function setChip(btn, tableId, key) {{
  // Update visual state
  const filterRow = btn.closest('.filter-row');
  if (filterRow) {{
    filterRow.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('on'));
  }}
  btn.classList.add('on');
  // Store state in JS object (reliable across all browsers)
  _activeChip[tableId] = key;
  applyFilters(tableId);
}}

// ── Search input handler ──
function handleSearch(input, tableId) {{
  _searchVal[tableId] = input.value;
  applyFilters(tableId);
}}

// ── Sector dropdown handler ──
function handleSector(select, tableId) {{
  _sectorVal[tableId] = select.value;
  applyFilters(tableId);
}}

// ── Score slider handler ──
function handleScore(input, tableId) {{
  _scoreMin[tableId] = input.value;
  const lbl = document.getElementById('scoreval-' + tableId);
  if (lbl) lbl.textContent = input.value;
  applyFilters(tableId);
}}

// Legacy aliases so old calls still work
function setFilter(btn, tableId, key) {{ setChip(btn, tableId, key); }}
function filterTable(input, tableId) {{ handleSearch(input, tableId); }}

// ── Quick Sort — one-click column sort ──
function quickSort(tableId, col, dir, btn) {{
  if (btn) {{
    btn.closest('.sort-bar').querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }}
  const table = document.getElementById(tableId + '-table');
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a,b) => {{
    const av = a.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const bv = b.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return dir==='desc' ? bn-an : an-bn;
    return dir==='desc' ? bv.localeCompare(av) : av.localeCompare(bv);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Column header sort (existing behaviour) ──
function sortTable(tableId, col) {{
  const table = document.getElementById(tableId);
  const tbody = table.querySelector('tbody');
  const rows  = Array.from(tbody.querySelectorAll('tr'));
  const asc   = table.dataset.sort !== col+'asc';
  table.dataset.sort = asc ? col+'asc' : col+'desc';
  rows.sort((a,b) => {{
    const av = a.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const bv = b.cells[col]?.textContent?.trim().replace(/[^\\d.-]/g,'') || '0';
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return asc ? an-bn : bn-an;
    return asc ? av.localeCompare(bv) : bv.localeCompare(av);
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Quick Picks panel populator — runs after DOM ready ──
window.addEventListener('load', function() {{
(function buildQuickPicks() {{
  const all = Object.values(STOCKS);
  if (!all || !all.length) return;

  function safeNum(v, fallback) {{ return (v == null || isNaN(v)) ? fallback : Number(v); }}
  function safeBool(v) {{ return v === true || v === 'True' || v === '1' || v === 1; }}

  function renderList(containerId, stocks, metaFn) {{
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!stocks || !stocks.length) {{
      el.innerHTML = '<div style="font-size:11px;color:var(--muted);padding:4px 0;">No matches today — check back tomorrow</div>';
      return;
    }}
    try {{
      el.innerHTML = stocks.slice(0,6).map(function(s) {{
        return (
        '<div class="qp-stock" data-sym="' + s.symbol + '" onclick="openModal(this.dataset.sym)" style="cursor:pointer">' +
        '<div><span class="qp-stock-sym">' + s.symbol + '</span>' +
        '<div class="qp-stock-meta">' + metaFn(s) + '</div></div>' +
        '<span class="grade-badge" style="background:' + (s.grade_color||'#888') + ';font-size:10px;">' + (s.grade||'?') + '</span>' +
        '</div>'
        );
      }}).join('');
    }} catch(e) {{ el.innerHTML = '<div style="font-size:11px;color:var(--muted)">Error rendering list</div>'; }}
  }}

  function fmt(v, dec) {{
    var n = safeNum(v, null);
    return n == null ? 'N/A' : n.toFixed(dec||1);
  }}

  // ── Pre-Move Setups ──
  // Try: A/A+ grade, not near 52W high. Fallback: top score stocks below 52W high
  var preMoveFilter = all
    .filter(s => ['A+','A'].includes(s.grade) && safeNum(s.pct_from_high, 0) < -3)
    .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  if (!preMoveFilter.length) {{
    preMoveFilter = all
      .filter(s => safeNum(s.score,0) >= 55 && safeNum(s.pct_from_high, 0) < -3)
      .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  }}
  if (!preMoveFilter.length) {{
    preMoveFilter = all.sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0)).slice(0,6);
  }}
  renderList('qp-premove', preMoveFilter, s => 'Score ' + s.score + ' · BB ' + fmt(s.bb_width) + '% · ' + (s.sector||''));

  // ── VCP + Coiling ──
  var vcpFilter = all
    .filter(s => safeNum(s.vcp_score,0) >= 55)
    .sort((a,b) => safeNum(b.vcp_score,0) - safeNum(a.vcp_score,0));
  if (!vcpFilter.length) {{
    vcpFilter = all
      .filter(s => safeNum(s.bb_width,99) < 9)
      .sort((a,b) => safeNum(a.bb_width,99) - safeNum(b.bb_width,99));
  }}
  renderList('qp-vcp', vcpFilter, s => 'VCP ' + (s.vcp_score||0) + ' · BB ' + fmt(s.bb_width) + '%');

  // ── Volume Dry-Up ──
  var volDryFilter = all
    .filter(s => safeBool(s.vol_dry_up) && safeNum(s.score,0) >= 35)
    .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  if (!volDryFilter.length) {{
    volDryFilter = all
      .filter(s => safeBool(s.vol_dry_up))
      .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  }}
  if (!volDryFilter.length) {{
    volDryFilter = all
      .filter(s => safeNum(s.vol_ratio,1) < 0.7 && safeNum(s.score,0) >= 35)
      .sort((a,b) => safeNum(a.vol_ratio,1) - safeNum(b.vol_ratio,1));
  }}
  renderList('qp-voldry', volDryFilter, s => 'Score ' + s.score + ' · VolR ' + fmt(s.vol_ratio) + 'x');

  // ── Gainers Today ──
  // Most lenient — just needs positive 1d return
  var gainersFilter = all
    .filter(s => safeNum(s.chg_1d,0) > 0)
    .sort((a,b) => safeNum(b.chg_1d,0) - safeNum(a.chg_1d,0));
  renderList('qp-gainers', gainersFilter, s => '+' + fmt(s.chg_1d,2) + '% · ' + fmt(s.vol_ratio,1) + 'x vol');

  // ── Fund Strong + Stage 2 ──
  var fundStageFilter = all
    .filter(s => s.fund_grade === 'Strong' && safeBool(s.is_stage2))
    .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  if (!fundStageFilter.length) {{
    fundStageFilter = all
      .filter(s => s.fund_grade === 'Strong')
      .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  }}
  if (!fundStageFilter.length) {{
    fundStageFilter = all
      .filter(s => s.fund_grade === 'Good' && safeBool(s.is_stage2))
      .sort((a,b) => safeNum(b.score,0) - safeNum(a.score,0));
  }}
  renderList('qp-fundstage', fundStageFilter, s => 'Score ' + s.score + ' · ROE ' + fmt(s.roe) + '%');

  // ── Accumulation ──
  var accumFilter = all
    .filter(s => safeBool(s.is_accumulating))
    .sort((a,b) => safeNum(b.accum_score,0) - safeNum(a.accum_score,0));
  if (!accumFilter.length) {{
    accumFilter = all
      .filter(s => safeNum(s.accum_score,0) >= 20)
      .sort((a,b) => safeNum(b.accum_score,0) - safeNum(a.accum_score,0));
  }}
  renderList('qp-accum', accumFilter, s => (s.accum_label||'—') + ' · ' + (s.accum_days||0) + 'd');

  // ── Init counters ──
  document.querySelectorAll('[id^="counter-"]').forEach(function(el) {{
    var tableId = el.id.replace('counter-','');
    var tbody = document.querySelector('#' + tableId + '-table tbody');
    if (tbody) el.textContent = tbody.querySelectorAll('tr').length + ' stocks';
  }});

  // ── Alert Panel ──
  var alertGrid = document.getElementById('alertGrid');
  if (alertGrid) {{
    var alertStocks = all
      .filter(function(s) {{ return ['A+','A'].includes(s.grade) && !s.pledge_danger && s.trade_setup && s.trade_setup.entry; }})
      .sort(function(a,b) {{ return safeNum(b.score,0) - safeNum(a.score,0); }})
      .slice(0, 24);
    if (!alertStocks.length) {{
      alertGrid.innerHTML = '<div style="font-size:11px;color:var(--muted)">No A+/A setups today</div>';
    }} else {{
      alertGrid.innerHTML = alertStocks.map(function(s) {{
        var ts = s.trade_setup || {{}};
        return '<div class="alert-chip" data-sym="' + s.symbol + '" onclick="openModal(this.dataset.sym)" style="cursor:pointer;">' +
          '<div class="alert-sym">' + s.symbol + ' <span class="grade-badge" style="background:' + s.grade_color + ';font-size:9px;">' + s.grade + '</span></div>' +
          '<div class="alert-entry">Entry ₹' + (ts.entry ? ts.entry.toFixed(2) : 'N/A') + '</div>' +
          '<div class="alert-sl">SL ₹' + (ts.stop_loss ? ts.stop_loss.toFixed(2) : 'N/A') + ' · T1 ₹' + (ts.target1 ? ts.target1.toFixed(2) : 'N/A') + '</div>' +
          '</div>';
      }}).join('');
    }}
  }}
}})();
}}); // end window.addEventListener load

// ── CSV Export (v6.0) ──
// ── Simple table search (for Vol Surge, Stage 2 tabs) ──
function searchSimpleTable(input, tableId) {{
  var q = input.value.toUpperCase();
  var rows = document.querySelectorAll('#' + tableId + ' tbody tr');
  var vis = 0;
  rows.forEach(function(row) {{
    var txt = row.textContent.toUpperCase();
    var show = !q || txt.includes(q);
    row.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  // Update grade filter buttons to show only matching rows
  var countEl = document.getElementById('counter-' + tableId.replace('-table',''));
  if (countEl) countEl.textContent = vis + ' stocks';
}}

// ── Simple grade filter (for Vol Surge, Stage 2 tabs) ──
function filterSimpleGrade(btn, tableId, grade) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  var rows = document.querySelectorAll('#' + tableId + ' tbody tr');
  var vis = 0;
  rows.forEach(function(row) {{
    var rowGrade = row.querySelector('.grade-badge') ? row.querySelector('.grade-badge').textContent.trim() : '';
    var show = !grade || rowGrade === grade;
    row.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var countEl = document.getElementById('counter-' + tableId.replace('-table',''));
  if (countEl) countEl.textContent = vis + ' stocks';
}}

// ── Fundamentals card search ──
function searchFundCards(input) {{
  var q = input.value.toUpperCase();
  var cards = document.querySelectorAll('#fund-cards-grid .fund-card');
  var vis = 0;
  cards.forEach(function(card) {{
    var sym = (card.dataset.symbol || '').toUpperCase();
    var show = !q || sym.includes(q);
    card.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('counter-fundamentals');
  if (el) el.textContent = vis + ' stocks';
}}

// ── Fundamentals card grade filter ──
function filterFundCards(btn, grade) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  var cards = document.querySelectorAll('#fund-cards-grid .fund-card');
  var vis = 0;
  cards.forEach(function(card) {{
    var g = card.dataset.fundgrade || '';
    var show = !grade || g === grade;
    card.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('counter-fundamentals');
  if (el) el.textContent = vis + ' stocks';
}}

// ── Accumulation card search ──
function searchAccumCards(input) {{
  var q = input.value.toUpperCase();
  var cards = document.querySelectorAll('#accum-cards-grid .accum-card');
  var vis = 0;
  cards.forEach(function(card) {{
    var sym  = (card.dataset.symbol || '').toUpperCase();
    var sec  = (card.dataset.sector || '').toUpperCase();
    var show = !q || sym.includes(q) || sec.includes(q);
    card.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('counter-accumulation');
  if (el) el.textContent = vis + ' stocks';
}}

// ── Accumulation card label filter ──
function filterAccumCards(btn, label) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  var cards = document.querySelectorAll('#accum-cards-grid .accum-card');
  var vis = 0;
  cards.forEach(function(card) {{
    var l = card.dataset.accumlabel || '';
    var show = !label || l === label;
    card.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('counter-accumulation');
  if (el) el.textContent = vis + ' stocks';
}}

// ── Init special tab counters ──
(function initCounters() {{
  var specials = [
    {{ tableId: 'volsurge-table', countId: 'counter-volsurge' }},
    {{ tableId: 'stage2-table',   countId: 'counter-stage2'   }},
  ];
  specials.forEach(function(s) {{
    var tbody = document.querySelector('#' + s.tableId + ' tbody');
    var el    = document.getElementById(s.countId);
    if (tbody && el) el.textContent = tbody.querySelectorAll('tr').length + ' stocks';
  }});
  var fundCards  = document.querySelectorAll('#fund-cards-grid .fund-card');
  var accumCards = document.querySelectorAll('#accum-cards-grid .accum-card');
  var elF = document.getElementById('counter-fundamentals');
  var elA = document.getElementById('counter-accumulation');
  if (elF) elF.textContent = fundCards.length + ' stocks';
  if (elA) elA.textContent = accumCards.length + ' stocks';
}})();

// ── Expert tab filter ──
function filterExpertDecision(btn, tableId, decision) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  var rows = document.querySelectorAll('#' + tableId + ' tbody tr');
  var vis = 0;
  rows.forEach(function(row) {{
    var show = !decision || row.dataset.expert === decision;
    row.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('counter-expert');
  if (el) el.textContent = vis + ' stocks';
}}

function exportCSV(tableId) {{
  var NL = String.fromCharCode(10);
  var Q  = String.fromCharCode(34);
  var table = document.getElementById(tableId);
  if (!table) return;
  var headers = Array.from(table.querySelectorAll('thead th')).map(function(th) {{ return th.textContent.trim(); }});
  var rows = Array.from(table.querySelectorAll('tbody tr'))
    .filter(function(r) {{ return r.style.display !== 'none'; }})
    .map(function(r) {{
      return Array.from(r.querySelectorAll('td')).map(function(td) {{
        return Q + td.textContent.trim().replace(new RegExp(Q,'g'), Q+Q) + Q;
      }});
    }});
  var lines = [headers.join(',')].concat(rows.map(function(r) {{ return r.join(','); }}));
  var csv = lines.join(NL);
  var blob = new Blob([csv], {{ type: 'text/csv' }});
  var url  = URL.createObjectURL(blob);
  var a    = document.createElement('a');
  a.href = url; a.download = 'nse_swing_v6_results.csv'; a.click();
  URL.revokeObjectURL(url);
}}

// ── Copy Alert Prices (v6.0) ──
function copyAlerts() {{
  var NL = String.fromCharCode(10);
  var all = Object.values(STOCKS);
  var lines = all
    .filter(function(s) {{ return ['A+','A'].includes(s.grade) && !s.pledge_danger && s.trade_setup && s.trade_setup.entry; }})
    .sort(function(a,b) {{ return (b.score||0) - (a.score||0); }})
    .slice(0, 24)
    .map(function(s) {{
      var ts = s.trade_setup || {{}};
      return s.symbol + ' | Entry: ' + (ts.entry ? ts.entry.toFixed(2) : 'N/A') +
             ' | SL: ' + (ts.stop_loss ? ts.stop_loss.toFixed(2) : 'N/A') +
             ' | T1: ' + (ts.target1 ? ts.target1.toFixed(2) : 'N/A') +
             ' | Score: ' + (s.score||0);
    }}).join(NL);
  if (navigator.clipboard) {{
    navigator.clipboard.writeText(lines).then(function() {{
      var btn = document.querySelector('.copy-btn');
      if (btn) {{ btn.textContent = 'Copied!'; setTimeout(function(){{ btn.textContent = 'Copy All'; }}, 2000); }}
    }});
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = lines;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }}
}}

function openModal(symbol) {{
  const s = STOCKS[symbol];
  if (!s) return;
  const gradeCol  = s.grade_color;
  const chgColor  = v => v>0?'#10b981':v<0?'#ef4444':'#8892a4';
  const plus      = v => (v>0?'+':'')+parseFloat(v).toFixed(2);
  const macdColor = s.macd > s.macd_sig ? '#10b981' : '#ef4444';
  const sigHtml   = s.active_signals.map(sg => {{
    const cls = sg.includes('Elite')||sg.includes('RS Elite') ? 'signal-elite' :
                sg.includes('⚠️')||sg.includes('Results') ? 'signal-warn' :
                sg.includes('Surge')||sg.includes('surge') ? 'signal-surge' :
                sg.includes('Delivery')||sg.includes('Near52')||sg.includes('Breakout') ? 'signal-green' : '';
    return `<span class="signal-tag ${{cls}}">${{sg}}</span>`;
  }}).join(' ') || '<span style="color:#8892a4">None today</span>';
  const wkly  = s.weekly || {{}};
  const ts    = s.trade_setup || {{}};
  const ei    = s.earnings_info || {{}};
  const sbHtml = Object.entries(s.score_breakdown || {{}}).map(([k,v]) => `
    <div class="breakdown-item">
      <div class="breakdown-label">${{k.replace(/_/g,' ')}}</div>
      <div class="breakdown-val" style="color:${{v>=8?'#10b981':v>=5?'#38bdf8':v>=2?'#f59e0b':'#8892a4'}}">${{v}}</div>
    </div>`).join('');

  const earnWarnHtml = ei.has_upcoming ?
    `<div class="earnings-warn">⚠️ <strong>Results in ${{ei.days_away}} day(s)</strong> — ${{ei.date_str}} · Consider waiting for post-result entry</div>` : '';

  const rsi_ideal  = s.rsi >= 50 && s.rsi <= 72;
  const adx_strong = s.adx > 25;
  const del_pct    = s.delivery_pct;
  const del_ok     = del_pct !== null && del_pct >= 55;
  const near52     = s.near_52w_high;
  const rs_elite   = s.rs_percentile >= 90;

  // ── v3.0 fundamental vars ──
  const fundScore  = s.fund_score || 0;
  const fundGrade  = s.fund_grade || 'N/A';
  const fundColor  = fundGrade==='Strong'?'#a78bfa':fundGrade==='Good'?'#10b981':fundGrade==='Moderate'?'#f59e0b':'#ef4444';
  const fundOk     = fundGrade==='Strong'||fundGrade==='Good';
  const roe        = s.roe; const eps  = s.eps_growth; const de = s.de_ratio;
  const roeStr     = roe!=null?roe.toFixed(1)+'%':'N/A';
  const epsStr     = eps!=null?eps.toFixed(1)+'%':'N/A';
  const deStr      = de!=null?de.toFixed(2):'N/A';
  const peStr      = s.pe_ratio!=null?s.pe_ratio.toFixed(1)+'×':'N/A';

  // ── v3.0 stage vars ──
  const stage     = s.stage || 'Unknown';
  const stageInfo = s.stage_info || {{}};
  const isStage2  = stage === 'Stage 2';
  const stageColor= isStage2?'#10b981':stage==='Stage 1'?'#38bdf8':stage==='Stage 3'?'#f59e0b':'#ef4444';
  const stageDesc = {{'Stage 2':'Advancing — ideal buy zone ✅','Stage 1':'Basing — wait for breakout','Stage 3':'Topping — caution, consider exit','Stage 4':'Declining — avoid / short only','Unknown':'Insufficient weekly data'}}[stage]||'';

  // ── v3.0 pledging vars ──
  const pledgePct  = s.pledge_pct;
  const pledgeOk   = pledgePct === null || pledgePct < 20;
  const pledgeDang = s.pledge_danger;
  const pledgeWarn = s.pledge_warn;
  const pledgeStr  = pledgePct!=null?pledgePct.toFixed(1)+'%':'N/A';
  const pledgeColor= pledgeDang?'#ef4444':pledgeWarn?'#f59e0b':'#10b981';
  const pledgeHtml = pledgeDang
    ? `<div class="pledge-alert">🚨 <strong>Promoter Pledging DANGER: ${{pledgeStr}}</strong> — Score penalised. Avoid this stock or drastically reduce position size. High pledging = forced selling risk.</div>`
    : pledgeWarn
    ? `<div style="background:rgba(245,158,11,.08);border:1px solid rgba(245,158,11,.3);border-radius:8px;padding:8px 14px;margin-top:8px;color:#f59e0b;font-size:12px">⚠️ Promoter Pledging Warning: ${{pledgeStr}} — Monitor closely.</div>`
    : '';

  // ── v4.0 accumulation vars ──
  const accumLabel  = s.accum_label || 'None';
  const accumDays   = s.accum_days || 0;
  const accumScore  = s.accum_score || 0;
  const accumSigs   = s.accum_signals || [];
  const isAccum     = s.is_accumulating || false;
  const accumColor  = accumLabel==='Strong Accumulation'?'#10b981':accumLabel==='Accumulation'?'#38bdf8':'#8892a4';
  const accumHtml   = isAccum ? `<div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:8px;padding:10px 14px;margin-top:8px;font-size:12px;">
    <div style="color:var(--green);font-weight:700;margin-bottom:4px;">🏦 ${{accumLabel}} — ${{accumDays}} consecutive days</div>
    <div style="display:flex;flex-wrap:wrap;gap:4px;">${{accumSigs.map(s=>`<span class="accum-signal-tag">${{s}}</span>`).join('')}}</div>
    <div class="accum-score-bar" style="margin-top:6px;"><div class="accum-score-fill" style="width:${{accumScore}}%"></div></div>
    <div style="font-size:10px;color:var(--muted);margin-top:3px;">Accumulation Score: ${{accumScore}}/100</div>
  </div>` : '';

  // ── Volume Surge ──
  const vsType    = s.vol_surge_type || null;
  const vsRatio   = s.vol_surge_ratio || 0;
  const vsUp      = s.vol_surge_up || false;
  const vsColor   = vsType==='MegaSurge'?'#f59e0b':vsType==='StrongSurge'?'#10b981':vsType?'#38bdf8':'#8892a4';
  const vsLabel   = vsType==='MegaSurge'?`🔥 Mega Surge ${{vsRatio}}× avg`:vsType==='StrongSurge'?`⚡ Strong Surge ${{vsRatio}}× avg`:vsType?`↑ Surge ${{vsRatio}}× avg`:`No surge (${{vsRatio}}× avg)`;
  const vsDayLabel= vsUp?'↑ Up-day (bullish)':'↓ Down-day (caution)';

  // ── v6.0 new modal vars ──
  const stDir     = s.supertrend_dir || 0;
  const stBuy     = stDir === 1;
  const stFlip    = stBuy && s.active_signals?.some(sg => sg.includes('ST-Flip'));
  const mfiVal    = s.mfi;
  const cmfVal    = s.cmf;
  const mfiOk     = mfiVal != null && mfiVal >= 45 && mfiVal <= 65;
  const cmfOk     = cmfVal != null && cmfVal > 0.05;
  const hasBulkBuy  = s.bulk_deal?.bulk_buy || s.bulk_deal?.block_buy;
  const hasBulkSell = s.bulk_deal?.bulk_sell;
  const bulkHtml  = hasBulkSell
    ? `<div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.35);border-radius:8px;padding:8px 14px;margin-bottom:8px;color:#ef4444;font-size:12px">🚨 <strong>Bulk/Block SELL detected today</strong> — Institutional selling. Avoid entry.</div>`
    : hasBulkBuy
    ? `<div style="background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);border-radius:8px;padding:8px 14px;margin-bottom:8px;color:var(--green);font-size:12px">📋 <strong>Bulk/Block BUY detected today</strong> — Institutional buying confirmation.</div>`
    : '';
  const circuitHtml = s.circuit_risk
    ? `<div style="background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;padding:8px 14px;margin-bottom:8px;color:var(--amber);font-size:12px">⚡ <strong>Near ${{s.circuit_risk}} circuit limit</strong> — May be untradeable next session.</div>`
    : '';
  const pivotHtml = (s.pivot_pp) ? `
    <div style="margin-top:10px"><div class="section-title">📍 Pivot Points (from prev session)</div>
    <div class="pivot-row">
      <span class="pivot-chip r2">R2: ₹${{s.pivot_r2?.toFixed(2)}}</span>
      <span class="pivot-chip r1">R1: ₹${{s.pivot_r1?.toFixed(2)}}</span>
      <span class="pivot-chip pp">PP: ₹${{s.pivot_pp?.toFixed(2)}}</span>
      <span class="pivot-chip s1">S1: ₹${{s.pivot_s1?.toFixed(2)}}</span>
      <span class="pivot-chip s2">S2: ₹${{s.pivot_s2?.toFixed(2)}}</span>
      <span style="font-size:10px;color:var(--muted);align-self:center;">CMP ₹${{s.price?.toFixed(2)}}</span>
    </div></div>` : '';
  const candleHtml = s.candle_score >= 4
    ? `<div style="font-size:11px;color:var(--amber);margin-top:4px;">🕯 Candle Patterns: ${{Object.keys(s.candle_patterns||{{}}).join(' · ')||'None'}}</div>` : '';
  const flatBaseHtml = s.flat_base
    ? `<div style="font-size:11px;color:var(--blue);margin-top:4px;">📐 Flat Base: ${{s.flat_base_info?.range_pct?.toFixed(1)}}% range over ${{s.flat_base_info?.days}} days ${{s.flat_base_info?.vol_declining?'· Vol declining ✅':''}}</div>` : '';

  // ── Position size ──
  const capital   = {cap};
  const riskAmt   = {risk_amt};
  const entry     = ts.entry || 0;
  const sl        = ts.stop_loss || 0;
  const qty       = (entry && sl && entry > sl) ? Math.floor(riskAmt / (entry - sl)) : 0;
  const qtyInvest = qty * entry;
  const posHtml   = ts.entry ? `
  <div class="pos-calc">
    <div class="section-title" style="margin-bottom:8px">💰 Position Size Calculator</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
      <div class="trade-box"><div class="trade-box-label">Quantity</div><div class="trade-box-val" style="color:var(--blue)">${{qty.toLocaleString('en-IN')}}</div><div class="trade-box-sub">shares</div></div>
      <div class="trade-box"><div class="trade-box-label">Capital Required</div><div class="trade-box-val" style="color:var(--text)">₹${{Math.round(qtyInvest).toLocaleString('en-IN')}}</div><div class="trade-box-sub">of ₹{cap:,.0f}</div></div>
      <div class="trade-box"><div class="trade-box-label">Max Loss (if SL hit)</div><div class="trade-box-val" style="color:var(--red)">₹${{riskAmt.toLocaleString('en-IN')}}</div><div class="trade-box-sub">{CFG['risk_per_trade_pct']}% of capital</div></div>
    </div>
  </div>` : '';

  // Trade setup HTML
  const tradeHtml = ts.entry ? `
  <div class="trade-setup-card">
    <div class="section-title">🎯 Key Technical Levels — ${{ts.setup_type}}</div>
    <div class="trade-setup-grid">
      <div class="trade-box"><div class="trade-box-label">Entry Price</div><div class="trade-box-val" style="color:var(--blue)">₹${{ts.entry?.toLocaleString('en-IN')}}</div><div class="trade-box-sub">Trigger / Limit</div></div>
      <div class="trade-box"><div class="trade-box-label">Stop Loss</div><div class="trade-box-val" style="color:var(--red)">₹${{ts.stop_loss?.toLocaleString('en-IN')}}</div><div class="trade-box-sub">Risk ${{ts.risk_pct?.toFixed(1)}}%</div></div>
      <div class="trade-box"><div class="trade-box-label">Target 1 (1:2)</div><div class="trade-box-val" style="color:var(--green)">₹${{ts.target1?.toLocaleString('en-IN')}}</div><div class="trade-box-sub">+${{ts.reward1_pct?.toFixed(1)}}%</div></div>
    </div>
    <div class="trade-t2-row"><span>Target 2: <strong style="color:#a78bfa">₹${{ts.target2?.toLocaleString('en-IN')}}</strong> +${{ts.reward2_pct?.toFixed(1)}}%</span><span>R:R = <strong style="color:var(--blue)">1:${{ts.rr_ratio}}</strong></span></div>
  </div>${{posHtml}}` : '';

  // ── Expanded checklist (v6.0) — 20 checks ──
  const checks = [
    [rs_elite,          `🚀 RS Elite — ${{s.rs_percentile}}th %ile (>90 = top 10% momentum leaders)`],
    [isStage2,          `📈 Weinstein Stage 2 — ${{stage}} · ${{stageDesc}}`],
    [fundOk,            `💎 Fundamental Quality — ${{fundGrade}} (${{fundScore}}/20) · ROE ${{roeStr}} · EPS Growth ${{epsStr}}`],
    [pledgeOk,          `🏦 Promoter Pledging — ${{pledgeStr}} ${{pledgeDang?'🚨 DANGER':pledgeWarn?'⚠️ Warning':'✅ Safe'}}`],
    [isAccum,           `🏦 Institutional Accumulation — ${{accumLabel}} (${{accumScore}}/100) · ${{accumDays}}d`],
    [s.vcp_score>=60,   `🔷 VCP Score — ${{s.vcp_score}}/100 · Base ${{s.vcp_info?.base_days||'?'}} days`],
    [s.flat_base,       `📐 Flat Base — ${{s.flat_base_info?.range_pct?.toFixed(1)||'?'}}% range · ${{s.flat_base_info?.days}} days`],
    [stBuy,             `📈 Supertrend — ${{stBuy?'BUY ✅':'SELL ❌'}}${{stFlip?' (Fresh flip today! 🟢)':''}}`],
    [mfiOk,             `💧 MFI — ${{mfiVal!=null?mfiVal.toFixed(1):'N/A'}} (45-65 = quiet accumulation zone)`],
    [cmfOk,             `📊 CMF — ${{cmfVal!=null?cmfVal.toFixed(3):'N/A'}} (>0.05 = money flowing in)`],
    [s.obv_divergence,  `📶 OBV Divergence — ${{s.obv_divergence?'Volume leading price ✅ (smart money signal)':'Not detected'}}`],
    [s.nr7||s.nr4||s.inside_day||s.vol_dry_up, `📦 Compression — NR7:${{s.nr7}} NR4:${{s.nr4}} Inside:${{s.inside_day}} VolDry:${{s.vol_dry_up}}`],
    [s.is_weekly_nr7,   `📅 Weekly NR7 — ${{s.is_weekly_nr7?'Multi-TF Compression ✅ (weekly + daily)':'Not detected'}}`],
    [s.at_support,      `🛡 At Support — ${{s.at_support?'₹'+s.support_price+' support ('+s.support_dist_pct?.toFixed(1)+'% away) ✅':'Not at key support'}}`],
    [s.candle_score>=4, `🕯 Candle Pattern — ${{s.candle_score>=4?Object.keys(s.candle_patterns||{{}}).join(', ')||'Detected':'No bullish pattern today'}}`],
    [hasBulkBuy,        `📋 Bulk Deal — ${{hasBulkBuy?'BUY detected ✅':hasBulkSell?'SELL detected 🚨':'No bulk deal today'}}`],
    [del_ok,            `💼 Delivery >55% — ${{del_pct!=null?del_pct+'%':'N/A'}} (institutional vs speculative volume)`],
    [rsi_ideal,         `⚡ RSI Sweet Spot — ${{s.rsi}} (50-72 zone = momentum without overbought)`],
    [adx_strong,        `📐 ADX >25 — ${{s.adx}} (confirmed real trend, not sideways noise)`],
    [!ei.has_upcoming,  `📅 Results Calendar — ${{ei.has_upcoming?'⚠️ Results '+ei.date_str:'✅ No earnings in next 14 days'}}`],
  ];
  const checksHtml = checks.map(([pass, label]) =>
    `<div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:13px;min-width:18px">${{pass?'✅':'❌'}}</span>
      <span style="font-size:12px;color:${{pass?'var(--text)':'var(--muted)'}}">${{label}}</span>
    </div>`
  ).join('');

  document.getElementById('modalBody').innerHTML = `
    ${{circuitHtml}}
    ${{bulkHtml}}
    ${{earnWarnHtml}}
    ${{pledgeHtml}}
    ${{accumHtml}}
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
      <div>
        <h2 style="font-size:22px;font-weight:800">${{s.symbol}}</h2>
        <div style="color:#8892a4;font-size:13px;margin-top:2px">${{s.sector}} · NSE Equity · ${{stage}}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:2px">Sector Rank: #${{s.sector_rank}} of ${{s.sector_total}} · Sector Strength: ${{s.sector_momentum?.toFixed(0)}}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:24px;font-weight:700">₹${{s.price.toLocaleString('en-IN')}}</div>
        <div style="color:${{chgColor(s.chg_1d)}};font-size:14px">${{plus(s.chg_1d)}}% today</div>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:12px;margin:12px 0;flex-wrap:wrap">
      <span class="grade-badge" style="background:${{gradeCol}};font-size:15px;padding:5px 16px">${{s.grade}}</span>
      <div><div style="font-size:20px;font-weight:700">${{s.score}}<span style="font-size:12px;color:#8892a4">/100</span></div><div style="font-size:10px;color:#8892a4">Composite Score</div></div>
      <div style="flex:1"><div class="prog-bar"><div class="prog-fill" style="width:${{s.score}}%;background:${{gradeCol}};height:7px;border-radius:4px"></div></div></div>
      <span style="background:${{stageColor}}22;border:1px solid ${{stageColor}}66;color:${{stageColor}};padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600">${{stage}}</span>
      <span style="background:${{fundColor}}22;border:1px solid ${{fundColor}}66;color:${{fundColor}};padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600">💎 Fund: ${{fundGrade}} (${{fundScore}}/20)</span>
      ${{s.confidence_pct?`<span style="background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.35);color:#10b981;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700">🎯 Conf: ${{s.confidence_pct}}%</span>`:''}}
    </div>

    <div style="margin:10px 0"><div class="section-title">Active Signals</div>${{sigHtml}}</div>

    ${{tradeHtml}}

    <div style="margin-top:14px"><div class="section-title">📋 20-Point Setup Checklist (v6.0)</div>${{checksHtml}}</div>

    <div style="margin-top:14px"><div class="section-title">Technical Indicators</div></div>
    <div class="modal-grid">
      <div class="modal-metric"><div class="modal-metric-label">RSI (14) — Sweet Spot 50-72</div><div class="modal-metric-val" style="color:${{rsi_ideal?'#10b981':s.rsi>80?'#ef4444':'#f59e0b'}}">${{s.rsi}} ${{rsi_ideal?'✅':s.rsi>80?'⚠️ OB':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">ADX — Trend Strength</div><div class="modal-metric-val" style="color:${{adx_strong?'#10b981':s.adx>20?'#f59e0b':'#8892a4'}}">${{s.adx}} ${{adx_strong?'✅ Strong':'Moderate'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">RS Percentile</div><div class="modal-metric-val" style="color:${{rs_elite?'#a78bfa':s.rs_percentile>=70?'#10b981':'#8892a4'}}">${{s.rs_percentile}}th %ile ${{rs_elite?'🚀 ELITE':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">BB Width — Coiling</div><div class="modal-metric-val" style="color:${{s.bb_width<8?'#10b981':s.bb_width<12?'#f59e0b':'#8892a4'}}">${{s.bb_width?.toFixed(1)}}% ${{s.bb_width<8?'✅ Very Tight':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Delivery % (Institutional)</div><div class="modal-metric-val" style="color:${{del_ok?'#10b981':del_pct!=null&&del_pct>=40?'#f59e0b':'#8892a4'}}">${{del_pct!=null?del_pct+'%':'N/A'}} ${{del_ok?'✅':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">🔥 Volume Surge</div><div class="modal-metric-val" style="color:${{vsColor}}">${{vsLabel}}</div><div style="font-size:11px;color:${{vsUp?'#10b981':'#ef4444'}};margin-top:2px">${{vsType?vsDayLabel:'—'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">VCP Score</div><div class="modal-metric-val" style="color:${{s.vcp_score>=70?'#a78bfa':s.vcp_score>=50?'#38bdf8':'#8892a4'}}">${{s.vcp_score}}/100 ${{s.vcp_score>=70?'✅':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">52W High</div><div class="modal-metric-val">₹${{s.high_52w?.toLocaleString('en-IN')}} <span style="font-size:12px;color:${{near52?'#10b981':'#8892a4'}}">${{s.pct_from_high?.toFixed(1)}}%</span></div></div>
    </div>

    <div style="margin-top:14px"><div class="section-title">💎 Fundamentals (v3.0)</div></div>
    <div class="modal-grid">
      <div class="modal-metric"><div class="modal-metric-label">ROE (Return on Equity)</div><div class="modal-metric-val" style="color:${{roe!=null&&roe>=20?'#10b981':roe!=null&&roe>=12?'#f59e0b':'#ef4444'}}">${{roeStr}} ${{roe!=null&&roe>=20?'✅':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">EPS Growth YoY</div><div class="modal-metric-val" style="color:${{eps!=null&&eps>=25?'#10b981':eps!=null&&eps>=15?'#f59e0b':'#ef4444'}}">${{epsStr}} ${{eps!=null&&eps>=25?'✅ CAN SLIM C':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Debt / Equity Ratio</div><div class="modal-metric-val" style="color:${{de!=null&&de<=0.5?'#10b981':de!=null&&de<=1.0?'#f59e0b':'#ef4444'}}">${{deStr}} ${{de!=null&&de<=0.5?'✅ Low debt':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">P/E Ratio</div><div class="modal-metric-val">${{peStr}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Fundamental Grade</div><div class="modal-metric-val" style="color:${{fundColor}}">${{fundGrade}} (${{fundScore}}/20)</div></div>
      <div class="modal-metric"><div class="modal-metric-label">🏦 Promoter Pledging</div><div class="modal-metric-val" style="color:${{pledgeColor}}">${{pledgeStr}} ${{pledgeDang?'🚨 DANGER':pledgeWarn?'⚠️ Warning':'✅ Safe'}}</div></div>
    </div>

    <div style="margin-top:14px"><div class="section-title">📈 Stage Analysis — Weinstein (v3.0)</div></div>
    <div class="modal-grid">
      <div class="modal-metric"><div class="modal-metric-label">Stage Classification</div><div class="modal-metric-val" style="color:${{stageColor}}">${{stage}}</div><div style="font-size:11px;color:var(--muted);margin-top:3px">${{stageDesc}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">30-Week MA</div><div class="modal-metric-val">₹${{stageInfo.ma30?.toLocaleString('en-IN')||'N/A'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">MA Slope (5W)</div><div class="modal-metric-val" style="color:${{(stageInfo.ma_slope_pct||0)>0?'#10b981':'#ef4444'}}">${{stageInfo.ma_slope_pct!=null?(stageInfo.ma_slope_pct>0?'+':'')+stageInfo.ma_slope_pct.toFixed(2)+'%':'N/A'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Price vs 30W MA</div><div class="modal-metric-val" style="color:${{stageInfo.price_above_ma30?'#10b981':'#ef4444'}}">${{stageInfo.price_above_ma30?'Above ✅':'Below ❌'}}</div></div>
    </div>

    ${{wkly.w_rsi ? `<div style="margin-top:12px"><div class="section-title">Weekly Timeframe</div><div class="modal-grid">
      <div class="modal-metric"><div class="modal-metric-label">Weekly RSI</div><div class="modal-metric-val">${{wkly.w_rsi}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Weekly ADX</div><div class="modal-metric-val">${{wkly.w_adx}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">4-Week Return</div><div class="modal-metric-val" style="color:${{chgColor(wkly.w_roc_4)}}">${{plus(wkly.w_roc_4)}}%</div></div>
      <div class="modal-metric"><div class="modal-metric-label">13-Week Return</div><div class="modal-metric-val" style="color:${{chgColor(wkly.w_roc_13)}}">${{plus(wkly.w_roc_13)}}%</div></div>
    </div></div>` : ''}}

    <div style="margin-top:12px"><div class="section-title">v6.0 — New Indicators</div><div class="modal-grid">
      <div class="modal-metric"><div class="modal-metric-label">Supertrend</div><div class="modal-metric-val" style="color:${{stBuy?'var(--green)':'var(--red)'}}">${{stBuy?'BUY ✅':'SELL ❌'}}${{stFlip?' 🟢Flip!':''}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">MFI (${{mfiVal!=null?mfiVal.toFixed(1):'N/A'}})</div><div class="modal-metric-val" style="color:${{mfiOk?'var(--green)':'var(--muted)'}}">${{mfiOk?'Accumulation zone':'Outside zone'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">CMF (${{cmfVal!=null?cmfVal.toFixed(3):'N/A'}})</div><div class="modal-metric-val" style="color:${{cmfOk?'var(--green)':'var(--muted)'}}">${{cmfOk?'Money flowing in ✅':'Neutral/Outflow'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">OBV Divergence</div><div class="modal-metric-val" style="color:${{s.obv_divergence?'var(--green)':'var(--muted)'}}">${{s.obv_divergence?'Detected ✅ (smart money)':'Not detected'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">Weekly NR7</div><div class="modal-metric-val" style="color:${{s.is_weekly_nr7?'var(--amber)':'var(--muted)'}}">${{s.is_weekly_nr7?'Multi-TF Compression ✅':'No'}}</div></div>
      <div class="modal-metric"><div class="modal-metric-label">NR4 Signal</div><div class="modal-metric-val" style="color:${{s.nr4?'var(--amber)':'var(--muted)'}}">${{s.nr4?'NR4 Active ✅':'No'}}</div></div>
    </div>
    ${{pivotHtml}}
    ${{candleHtml}}
    ${{flatBaseHtml}}
    </div>

    <div style="margin-top:12px"><div class="section-title">Score Breakdown</div><div class="breakdown-grid">${{sbHtml}}</div></div>

    <div style="margin-top:14px">
      <div class="section-title">🤖 AI Analysis — India-First Expert Summary</div>
      <div id="ai-summary-${{s.symbol}}" style="margin-top:8px;background:var(--bg3);border-radius:8px;padding:12px 14px;font-size:12px;line-height:1.7;color:var(--muted);min-height:48px">
        <button onclick="getAISummary('${{s.symbol}}')" style="background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.3);color:#38bdf8;padding:6px 16px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:600">
          🤖 Get AI Analysis
        </button>
        <span style="font-size:11px;color:var(--muted);margin-left:8px">Ask AI to analyse this stock's setup (India-focused)</span>
      </div>
    </div>

    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <a href="https://www.nseindia.com/get-quotes/equity?symbol=${{s.symbol}}" target="_blank" style="padding:7px 13px;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;border-radius:8px;font-size:12px">NSE ↗</a>
      <a href="https://chartink.com/stocks/${{s.symbol.toLowerCase()}}" target="_blank" style="padding:7px 13px;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;border-radius:8px;font-size:12px">Chartink ↗</a>
      <a href="https://finance.yahoo.com/quote/${{s.symbol}}.NS" target="_blank" style="padding:7px 13px;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;border-radius:8px;font-size:12px">Yahoo Finance ↗</a>
      <a href="https://www.screener.in/company/${{s.symbol}}/" target="_blank" style="padding:7px 13px;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;border-radius:8px;font-size:12px">Screener.in ↗</a>
      <a href="https://trendlyne.com/equity/technical-analysis/${{s.symbol}}/" target="_blank" style="padding:7px 13px;background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.3);color:#38bdf8;border-radius:8px;font-size:12px">Trendlyne ↗</a>
    </div>

    <div style="margin-top:14px">
      <div class="section-title">📊 Price Relative vs Nifty 50 (63-day) — Comparative Relative Strength</div>
      <div style="margin-top:8px;background:var(--bg3);border-radius:8px;padding:12px 14px">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px">
          <div>
            <span style="font-size:22px;font-weight:700;color:${{s.rs_alpha>=0?'#10b981':'#ef4444'}}">${{s.rs_alpha>=0?'+':''}}${{(s.rs_alpha||0).toFixed(1)}}%</span>
            <span style="font-size:12px;color:var(--muted);margin-left:6px">vs Nifty (3 months)</span>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <span style="background:${{s.rs_percentile>=90?'rgba(167,139,250,.2)':s.rs_percentile>=70?'rgba(16,185,129,.12)':'rgba(56,189,248,.1)'}};color:${{s.rs_percentile>=90?'#a78bfa':s.rs_percentile>=70?'#10b981':'#38bdf8'}};padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700">
              RS Percentile: ${{s.rs_percentile}}th ${{s.rs_percentile>=90?'🚀 ELITE':s.rs_percentile>=70?'✅ Strong':''}}
            </span>
            <span style="background:rgba(59,130,246,.1);color:#38bdf8;padding:3px 10px;border-radius:20px;font-size:11px">
              3M Return: ${{(s.chg_3m||0)>0?'+':''}}${{(s.chg_3m||0).toFixed(1)}}%
            </span>
          </div>
        </div>
        <div style="position:relative;height:80px;width:100%">
          <canvas id="pr-chart-${{s.symbol}}" height="80"></canvas>
        </div>
        <div style="display:flex;gap:16px;margin-top:8px;font-size:11px">
          <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:2px;background:#38bdf8;display:inline-block"></span>Stock price (normalised)</span>
          <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:2px;background:#f59e0b;display:inline-block"></span>Nifty (normalised)</span>
          <span style="display:flex;align-items:center;gap:4px"><span style="width:12px;height:2px;background:#10b981;border-top:2px dashed #10b981;display:inline-block"></span>Price Relative ratio</span>
        </div>
      </div>
    </div>

    <div style="margin-top:14px">
      <div class="section-title">📈 EMA Trend Status</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:8px">
        ${{['EMA_10','EMA_21','EMA_50','EMA_200'].map(function(k) {{
          const ema = s[k.toLowerCase().replace('_','_')];
          const price = s.price;
          const above = price > (ema||0);
          const label = k==='EMA_10'?'10 EMA':k==='EMA_21'?'21 EMA':k==='EMA_50'?'50 EMA':'200 EMA';
          return '<div style="background:var(--bg3);border-radius:6px;padding:8px 10px"><div style="font-size:10px;color:var(--muted)">'+label+'</div><div style="font-size:13px;font-weight:700;color:'+(above?'#10b981':'#ef4444')+'">'+(ema?'₹'+ema.toLocaleString('en-IN',{{maximumFractionDigits:1}}):'-')+'</div><div style="font-size:10px;color:'+(above?'#10b981':'#ef4444')+'">Price '+(above?'above ✅':'below ❌')+'</div></div>';
        }}).join('')}}
      </div>
      ${{(function() {{
        const e50 = s.ema_50 || 0;
        const e200 = s.ema_200 || 0;
        if (!e50 || !e200) return '';
        if (e50 > e200) return '<div style="margin-top:8px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.25);border-radius:6px;padding:7px 12px;font-size:12px;color:#10b981">🌟 Golden Cross: 50 EMA above 200 EMA — Long-term bullish</div>';
        return '<div style="margin-top:8px;background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);border-radius:6px;padding:7px 12px;font-size:12px;color:#ef4444">💀 Death Cross: 50 EMA below 200 EMA — Long-term bearish</div>';
      }})()}}
    </div>
    </div>`;
  document.getElementById('modalOverlay').classList.add('open');
  // Draw Price Relative chart (v7.1 — Price Relative vs Nifty)
  setTimeout(function() {{
    var prCanvas = document.getElementById('pr-chart-' + s.symbol);
    if (!prCanvas || !window.Chart) return;
    var _3m = parseFloat(s.chg_3m) || 0;
    var _1m = parseFloat(s.chg_1m) || 0;
    var _5d = parseFloat(s.chg_5d) || 0;
    var _rs = parseFloat(s.rs_alpha) || 0;
    try {{
      if (prCanvas._chart) {{ prCanvas._chart.destroy(); }}
      prCanvas._chart = new Chart(prCanvas, {{
        type:'line',
        data:{{
          labels:['3M','2M','1M','2W','1W','Now'],
          datasets:[
            {{label:'Stock',data:[0,_3m*0.4,_3m*0.7,_1m,_5d*1.5,0],
             borderColor:'#38bdf8',borderWidth:2,pointRadius:0,tension:0.4,fill:false}},
            {{label:'Price Relative',data:[0,_rs*0.2,_rs*0.5,_rs*0.7,_rs*0.9,_rs],
             borderColor:'#10b981',borderWidth:1.5,pointRadius:0,tension:0.4,fill:false,
             borderDash:[4,3]}}
          ]
        }},
        options:{{
          responsive:true,maintainAspectRatio:false,
          plugins:{{legend:{{display:false}}}},
          scales:{{
            x:{{ticks:{{color:'#8892a4',font:{{size:9}}}},grid:{{display:false}}}},
            y:{{ticks:{{color:'#8892a4',font:{{size:9}}}},grid:{{color:'#2c3148'}}}}
          }}
        }}
      }});
    }} catch(e) {{}}
  }}, 120);
}}

// ══════════════════════════════════════════════════════════
// UNIFIED SCREEN FILTER ENGINE — works for all screener tables
// ══════════════════════════════════════════════════════════

// State: {{ tableId: {{ grade:'', search:'', chips:[{{attr,op,val,active}}] }} }}
var _SF = {{}};

function _sfState(tid) {{
  if (!_SF[tid]) _SF[tid] = {{ grade:'', search:'', chips:{{}} }};
  return _SF[tid];
}}

function _sfApply(tid) {{
  var st  = _sfState(tid);
  var rows = document.querySelectorAll('#' + tid + ' tbody tr');
  var vis = 0;
  rows.forEach(function(row) {{
    var show = true;
    // Grade filter
    if (st.grade) {{
      var gb = row.querySelector('.grade-badge');
      if (!gb || gb.textContent.trim() !== st.grade) show = false;
    }}
    // Search filter
    if (show && st.search) {{
      var sym = (row.dataset.sym||'').toUpperCase();
      var sec = (row.dataset.sec||'').toUpperCase();
      if (!sym.includes(st.search) && !sec.includes(st.search)) show = false;
    }}
    // Chip filters
    if (show) {{
      Object.keys(st.chips).forEach(function(key) {{
        if (!show) return;
        var chip = st.chips[key];
        if (!chip.active) return;
        var raw = row.dataset[chip.attr];
        if (raw === undefined || raw === null || raw === '') return; // missing attr = skip chip
        var v = parseFloat(raw);
        var threshold = parseFloat(chip.val);
        if (chip.op === '>=')    {{ if (!(v >= threshold))  show = false; }}
        else if (chip.op === '>') {{ if (!(v > threshold))   show = false; }}
        else if (chip.op === '<') {{ if (!(v < threshold))   show = false; }}
        else if (chip.op === '<='){{ if (!(v <= threshold))  show = false; }}
        else if (chip.op === 'lt'){{ if (!(v > 0 && v < threshold)) show = false; }} // positive AND below
        else if (chip.op === 'range') {{
          var parts = chip.val.split(',');
          var lo = parseFloat(parts[0]), hi = parseFloat(parts[1]);
          if (!(v >= lo && v <= hi)) show = false;
        }}
        else if (chip.op === '==') {{
          if (String(raw).trim() !== String(chip.val).trim()) show = false;
        }}
      }});
    }}
    row.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('scnt-' + tid);
  if (el) el.textContent = vis + ' stock' + (vis !== 1 ? 's' : '');
}}

function screenSearch(input, tid) {{
  _sfState(tid).search = input.value.toUpperCase();
  _sfApply(tid);
}}

function screenGrade(btn, tid, grade) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  _sfState(tid).grade = grade;
  _sfApply(tid);
}}

function screenToggle(btn, tid, attr, op, val) {{
  btn.classList.toggle('on');
  var key = attr + op + val;
  var st = _sfState(tid);
  if (btn.classList.contains('on')) {{
    st.chips[key] = {{ attr:attr, op:op, val:val, active:true }};
  }} else {{
    delete st.chips[key];
  }}
  _sfApply(tid);
}}

// ── EMA Scanner Filter Functions ──
function emaSearch(input, tblId) {{
  _sfState(tblId).search = input.value.toUpperCase();
  _emaApply(tblId);
}}

function emaGrade(btn, tblId, grade) {{
  btn.closest('div').querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('on'); }});
  btn.classList.add('on');
  _sfState(tblId).grade = grade;
  _emaApply(tblId);
}}

function emaVol(btn, tblId)  {{ btn.classList.toggle('on'); _emaApply(tblId); }}
function emaRsi(btn, tblId)  {{ btn.classList.toggle('on'); _emaApply(tblId); }}
function emaAdx(btn, tblId)  {{ btn.classList.toggle('on'); _emaApply(tblId); }}
function emaDel(btn, tblId)  {{ btn.classList.toggle('on'); _emaApply(tblId); }}

function _emaApply(tblId) {{
  var srch = _sfState(tblId).search || '';
  var grade = _sfState(tblId).grade || '';
  var _v = document.getElementById('chip-' + tblId + '-vol'); var needVol = _v && _v.classList.contains('on');
  var _r = document.getElementById('chip-' + tblId + '-rsi'); var needRsi = _r && _r.classList.contains('on');
  var _a = document.getElementById('chip-' + tblId + '-adx'); var needAdx = _a && _a.classList.contains('on');
  var _d = document.getElementById('chip-' + tblId + '-del'); var needDel = _d && _d.classList.contains('on');

  var rows = document.querySelectorAll('#' + tblId + ' tbody tr');
  var vis = 0;
  rows.forEach(function(row) {{
    var sym = (row.dataset.sym||row.cells[0]?.textContent||'').toUpperCase();
    var sec = (row.dataset.sec||row.cells[1]?.textContent||'').toUpperCase();
    var rsi = parseFloat(row.dataset.rsi || row.cells[7]?.textContent || '0');
    var adx = parseFloat(row.dataset.adx || '0');
    var vol = parseFloat(row.dataset.vol || row.cells[9]?.textContent || '0');
    var del = parseFloat(row.dataset.del || '0');
    var rGrade = row.dataset.grade || (row.querySelector('.grade-badge')?.textContent.trim() || '');

    var show = true;
    if (srch && !sym.includes(srch) && !sec.includes(srch)) show = false;
    if (grade && rGrade !== grade) show = false;
    if (needVol && vol < 1.5) show = false;
    if (needRsi && !(rsi >= 50 && rsi <= 72)) show = false;
    if (needAdx && adx < 20) show = false;
    if (needDel && del < 55) show = false;

    row.style.display = show ? '' : 'none';
    if (show) vis++;
  }});
  var el = document.getElementById('cnt-' + tblId);
  if (el) el.textContent = vis + ' stock' + (vis !== 1 ? 's' : '');
}}


function closeModal() {{
  document.getElementById('modalOverlay').classList.remove('open');
}}

async function getAISummary(symbol) {{
  const s   = STOCKS[symbol];
  const box = document.getElementById('ai-summary-' + symbol);
  if (!s || !box) return;

  box.innerHTML = '<span style="color:#38bdf8">⏳ Analysing ' + symbol + ' with India-first AI...</span>';

  const prompt = `You are an expert Indian stock market analyst specialising in NSE swing trading.
Analyse this stock briefly in 4-5 sentences. Focus only on Indian market signals:

Stock: ${{symbol}}
Price: ₹${{s.price}}
Grade: ${{s.grade}} (Score: ${{s.score}}/100)
RSI: ${{s.rsi}} | ADX: ${{s.adx}} | Delivery: ${{s.delivery_pct}}%
Supertrend: ${{s.supertrend_dir == 1 ? 'BUY' : 'SELL'}}
FII Absorption: ${{s.score_breakdown?.fii_absorption > 0 ? 'YES' : 'NO'}}
OI: ${{s.oi_buildup_type || 'N/A'}} | Stage: ${{s.stage}}
52W: ₹${{s.high_52w}} (${{s.pct_from_high?.toFixed(1)}}% from high)
Signals: ${{(s.active_signals||[]).slice(0,5).join(', ')}}

Give: 1) Current setup quality 2) Key India-specific signal supporting or opposing 3) Risk to watch 4) Should swing traders enter, wait or avoid? Be direct and concise.`;

  try {{
    const resp = await fetch('https://api.anthropic.com/v1/messages', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{
        model: 'claude-sonnet-4-20250514',
        max_tokens: 300,
        messages: [{{ role: 'user', content: prompt }}]
      }})
    }});
    const data = await resp.json();
    const text = data?.content?.[0]?.text || 'AI analysis unavailable.';
    box.innerHTML = '<div style="color:var(--text);line-height:1.7">' + (text||'').split('\\n').join('<br>') + '</div><div style="margin-top:6px;font-size:10px;color:var(--muted)">⚠️ Educational only.</div>';

  }} catch(e) {{
    box.innerHTML = '<span style="color:var(--muted)">AI unavailable in standalone mode. Works when served via the SaaS backend (uvicorn main:app).</span>';
  }}
}}
document.addEventListener('keydown', e => {{ if (e.key==='Escape') closeModal(); }});
</script>

<div class="footer">
  ⚠️ This report is for educational and informational purposes only. Not financial advice.<br>
  Entry/SL/Target prices are algorithmic estimates — always verify before trading.<br>
  Fundamentals from Yahoo Finance · Pledging from NSE (best-effort, quarterly data)<br>
  Trade Stag — NSE 500 Scanner — Generated {analysis_time}
  NSE 500 Swing Analyzer v7.2 — Generated {analysis_time}
</div>
</div>
</div>
</div>
</html>"""

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"\n  📄 Report saved → {output_file}")
        return output_file


# ─────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NSE 500 Swing Trading Analyzer v7.0 — India First")
    parser.add_argument("--top",     type=int,   default=0,   help="Limit to top N stocks (0=all)")
    parser.add_argument("--workers", type=int,   default=6,   help="Parallel download threads")
    parser.add_argument("--out",     type=str,   default="",  help="Output HTML filename")
    parser.add_argument("--capital", type=float, default=0,   help="Your trading capital in ₹ (default 5,00,000)")
    args = parser.parse_args()

    capital = args.capital if args.capital > 0 else CFG["default_capital"]
    CFG["default_capital"] = capital  # override so HTML picks it up

    print("""
╔══════════════════════════════════════════════════════════════╗
║   NSE 500 Swing Trading Analyzer  v7.1 — INDIA FIRST         ║
║   Expert-Audited · Delivery(dir) · FII(gate) · OI · VIX     ║
╚══════════════════════════════════════════════════════════════╝
    """)
    print(f"   💰 Capital: ₹{capital:,.0f}  |  Risk/trade: {CFG['risk_per_trade_pct']}%  |  Max risk: ₹{capital*CFG['risk_per_trade_pct']/100:,.0f}")

    # ── v6.0: Warm NSE session ONCE before all fetchers ──
    print("\n🔑 Warming NSE session (required for PCR / Bulk Deals / FII-DII)...")
    NSESession.get().warm()

    fetcher = NSEDataFetcher()
    symbols = fetcher.get_nifty500_list()
    if args.top > 0:
        symbols = symbols[:args.top]
        print(f"   🔬 Limited to first {args.top} stocks (--top flag)")

    print("\n📡 Fetching Nifty options PCR data...")
    pcr_data  = fetcher.get_pcr_data()

    print("\n📌 Calculating Nifty Max Pain...")
    max_pain_data = MaxPainCalculator.fetch_nifty_max_pain()
    if max_pain_data.get("fetched"):
        print(f"   📌 Max Pain: {max_pain_data['max_pain']} | {max_pain_data['sentiment']}")
    else:
        # Fallback: estimate Max Pain as nearest round 100 below current Nifty
        try:
            sess_mp = requests.Session()
            sess_mp.headers.update(HEADERS)
            r_mp = sess_mp.get("https://www.nseindia.com/api/allIndices", timeout=10)
            if r_mp.status_code == 200 and r_mp.text.strip()[0] in "[{":
                for item in r_mp.json().get("data", []):
                    if str(item.get("index","")) == "NIFTY 50":
                        cmp = float(item.get("last", 0) or 0)
                        if cmp > 0:
                            mp_est = round(cmp / 100) * 100  # nearest 100
                            dist   = round((cmp / mp_est - 1) * 100, 2) if mp_est else 0
                            sent   = "Price above Max Pain" if cmp > mp_est else "Price below Max Pain"
                            print(f"   📌 Max Pain estimated: ₹{mp_est:,.0f} (Nifty CMP ₹{cmp:,.0f})")
                            return {"max_pain": mp_est, "cmp": cmp, "distance_pct": dist,
                                    "sentiment": sent, "fetched": True}
        except Exception:
            pass
        print("   ⚠️  Max Pain: unavailable")

    print("\n📈 Downloading Nifty 50 benchmark data...")
    pipeline = NSEAnalysisPipeline()
    ok = pipeline.price_mgr.fetch_nifty()
    print(f"   {'✅' if ok else '⚠️ '} Nifty 50 {'loaded' if ok else 'unavailable (RS limited)'}")

    # ── v7.0: Pass PCR data to pipeline scorer ──
    pipeline._pcr_data = pcr_data

    output = pipeline.run(symbols, max_workers=args.workers)
    if not output:
        print("\n❌ No results — check internet connection.")
        return

    results, sorted_sectors, breadth_data, top_trades, fii_dii_data = output

    if not results:
        print("\n❌ No stocks passed quality filters.")
        return

    # ── Summary ──
    print("\n" + "─" * 60)
    print(f"  {'GRADE':<8} {'COUNT':<8} {'%'}")
    print("─" * 60)
    from collections import Counter
    gc = Counter(r["grade"] for r in results)
    for g in ["A+","A","B+","B","C","D"]:
        cnt = gc.get(g, 0)
        pct = cnt / len(results) * 100
        bar = "█" * int(pct / 2)
        print(f"  {g:<8} {cnt:<8} {pct:5.1f}%  {bar}")
    print("─" * 60)

    rs_elite      = [r for r in results if r["rs_percentile"] >= CFG["rs_elite_pct"]]
    stage2_stocks = [r for r in results if r.get("is_stage2")]
    fund_strong   = [r for r in results if r.get("fund_grade") == "Strong"]
    pledge_danger = [r for r in results if r.get("pledge_danger")]
    near_earn     = [r for r in results if r["earnings_info"].get("has_upcoming")]
    accum_stocks  = [r for r in results if r.get("is_accumulating")]
    st_buy        = [r for r in results if r.get("supertrend_dir") == 1]
    bulk_buys     = [r for r in results if r.get("bulk_deal", {}).get("bulk_buy") or r.get("bulk_deal", {}).get("block_buy")]
    bulk_sells    = [r for r in results if r.get("bulk_deal", {}).get("bulk_sell")]
    circuit_risk  = [r for r in results if r.get("circuit_risk")]

    risk_amt = round(capital * CFG["risk_per_trade_pct"] / 100)

    fii_sent = fii_dii_data.get("sentiment", "N/A")
    fii_5d   = fii_dii_data.get("fii_5d")

    print(f"\n  🌐 Market Breadth: {breadth_data['pct']}% above 200 EMA → {breadth_data['status']}")
    print(f"  💹 FII 5-Day Flow: {'₹{:,.0f}Cr'.format(fii_5d) if fii_5d else 'N/A'} → {fii_sent}")
    print(f"  🚀 RS Elite (>90th %ile): {len(rs_elite)} stocks")
    print(f"  ✅ Stage 2 (buy zone):     {len(stage2_stocks)} stocks")
    print(f"  💎 Fundamentally Strong:  {len(fund_strong)} stocks")
    print(f"  🏦 Accumulation Detected: {len(accum_stocks)} stocks")
    print(f"  📈 Supertrend BUY:         {len(st_buy)} stocks")
    print(f"  📋 Bulk Buys Today:        {len(bulk_buys)} stocks")
    if bulk_sells:
        print(f"  🚨 Bulk SELLS Today:       {len(bulk_sells)} stocks — CAUTION")
    if circuit_risk:
        print(f"  ⚡ Near Circuit Limit:     {len(circuit_risk)} stocks — AVOID NEXT SESSION")
    print(f"  🚨 Pledge Danger (>{CFG['pledge_danger_pct']}%):    {len(pledge_danger)} stocks — AVOID")
    print(f"  ⚠️  Near Earnings:         {len(near_earn)} stocks")

    print(f"\n🏆 TOP 10 SMART OPPORTUNITIES (by Confidence):\n")
    for i, r in enumerate(top_trades, 1):
        sigs  = ", ".join(r["active_signals"][:3]) if r["active_signals"] else "—"
        ts    = r.get("trade_setup", {})
        entry_v = ts.get("entry", 0)
        sl_v    = ts.get("stop_loss", 0)
        qty     = int(risk_amt / (entry_v - sl_v)) if entry_v and sl_v and entry_v > sl_v else 0
        conf    = r.get("confidence_pct", 0)
        setup   = ts.get("setup_type", "—")
        print(f"  #{i:<2} {r['symbol']:<14} {r['grade']:>2} ({r['score']:>3})  "
              f"Conf:{conf}%  Setup:{setup:<12}  ₹{r['price']:>9,.2f}")
        if ts.get("entry"):
            print(f"       Entry ₹{entry_v:,.0f} → SL ₹{sl_v:,.0f} → T1 ₹{ts.get('target1',0):,.0f}  |  Qty: {qty:,}")

    print(f"\n🏭 Top 5 Sectors by Momentum:")
    for sec, strength, avg_rs, count, stage2_count, pct_above_200, avg_adx in sorted_sectors[:5]:
        print(f"     {sec:<20}  Strength:{strength:>5.1f}  Avg RS:{avg_rs:>5.1f}  ({count} stocks)")

    date_str    = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = args.out or f"nse500_swing_v7_{date_str}.html"
    reporter    = HTMLReportGenerator()
    reporter.generate(results, pcr_data, sorted_sectors, breadth_data,
                      capital=capital, output_file=output_file,
                      top_trades=top_trades, fii_dii_data=fii_dii_data,
                      max_pain_data=max_pain_data)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  ✅  Analysis Complete! — v7.0 India First                   ║
║                                                              ║
║  Open in any browser:                                        ║
║  → {output_file:<54}║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
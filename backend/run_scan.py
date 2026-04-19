"""
Trade Stag — Local NSE 500 Scanner
===================================
Run this on your PC to generate full NSE 500 analysis, then push to Render.

Usage:
  cd backend
  python run_scan.py          # Full NSE 500 scan → saves scan_cache.json
  python run_scan.py --limit 200   # Test with fewer stocks

After scan completes:
  cd ..
  git add backend/scan_cache.json
  git commit -m "Update scan data"
  git push
"""

import os, sys, json, time
from datetime import datetime

# Ensure analyzer.py is importable
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 65)
print("  Trade Stag — NSE 500 Local Scanner")
print("=" * 65)

# ── Parse args ──
limit = None
if "--limit" in sys.argv:
    idx = sys.argv.index("--limit")
    if idx + 1 < len(sys.argv):
        limit = int(sys.argv[idx + 1])
        print(f"  ⚙️  Universe limit: {limit} stocks")

try:
    from analyzer import (
        NSESession, NSEDataFetcher, NSEAnalysisPipeline,
        MaxPainCalculator, CFG
    )
    print("  ✅ Analyzer engine loaded")
except ImportError as e:
    print(f"  ❌ Cannot import analyzer: {e}")
    print("  Make sure analyzer.py is in the backend/ folder")
    sys.exit(1)

# ── Import _normalize_stock from main.py ──
# We import the helper functions inline to avoid starting the FastAPI server
from main import _normalize_stock, _grade_dist, _adv_dec

print(f"\n🚀 Starting NSE 500 scan at {datetime.now().strftime('%I:%M %p, %d %b %Y')}")
start_time = time.time()

# ── Step 1: Warm NSE session ──
print("\n🔑 Warming NSE session...")
NSESession.get().warm()

# ── Step 2: Fetch symbol list ──
fetcher = NSEDataFetcher()
symbols = fetcher.get_nifty500_list()
print(f"   📋 Got {len(symbols)} symbols")

if limit and len(symbols) > limit:
    print(f"   🔻 Capping to {limit} stocks (--limit flag)")
    symbols = symbols[:limit]

# ── Step 3: Fetch market-wide data ──
print("\n📊 Fetching market-wide data (PCR, Max Pain)...")
pcr_data = fetcher.get_pcr_data()
max_pain_data = MaxPainCalculator.fetch_nifty_max_pain()

# ── Step 4: Run full pipeline ──
pipeline = NSEAnalysisPipeline()
pipeline.price_mgr.fetch_nifty()
pipeline._pcr_data = pcr_data

# Use 6 workers locally (your PC has plenty of RAM)
output = pipeline.run(symbols, max_workers=6)

if not output:
    print("\n❌ Scan returned no results!")
    sys.exit(1)

results, sorted_sectors, breadth_data, top_trades, fii_dii_data = output
print(f"\n✅ Pipeline complete: {len(results)} stocks analyzed")

# ── Step 5: Normalize all results ──
print("🔄 Normalizing results for API...")
normalized_results = [_normalize_stock(r) for r in results]
normalized_top_trades = [_normalize_stock(t) for t in top_trades]

sectors = [
    {
        "name": s[0], "strength": s[1], "avg_rs": s[2],
        "count": s[3], "stage2_count": s[4],
        "pct_above_200": s[5], "avg_adx": s[6]
    }
    for s in sorted_sectors
]

market_pulse = {
    "breadth": breadth_data,
    "fii_dii": fii_dii_data,
    "pcr": pcr_data,
    "max_pain": max_pain_data,
    "total_stocks": len(normalized_results),
    "grade_distribution": _grade_dist(results),
    "advance_decline": _adv_dec(results),
}

last_scan = datetime.now().isoformat()

# ── Step 6: Save to scan_cache.json ──
cache = {
    "results": normalized_results,
    "top_trades": normalized_top_trades,
    "sectors": sectors,
    "breadth": breadth_data,
    "fii_dii": fii_dii_data,
    "pcr": pcr_data,
    "max_pain": max_pain_data,
    "market_pulse": market_pulse,
    "last_scan": last_scan,
}

cache_file = os.path.join(os.path.dirname(__file__), "scan_cache.json")
with open(cache_file, "w", encoding="utf-8") as f:
    json.dump(cache, f, default=str)

file_size_mb = os.path.getsize(cache_file) / (1024 * 1024)
elapsed = time.time() - start_time

# ── Count scanner tab stats ──
counts = {
    "all": len(normalized_results),
    "aplus": sum(1 for r in normalized_results if r.get("flag_aplus")),
    "expert": sum(1 for r in normalized_results if r.get("flag_expert_pick")),
    "trade": sum(1 for r in normalized_results if r.get("flag_strong_grade") and not r.get("pledge_danger")),
    "breakouts": sum(1 for r in normalized_results if r.get("flag_breakout")),
    "volsurge": sum(1 for r in normalized_results if r.get("flag_vol_surge")),
    "accumulation": sum(1 for r in normalized_results if r.get("flag_accumulation")),
    "ema": sum(1 for r in normalized_results if r.get("flag_ema_scanner")),
    "vcp": sum(1 for r in normalized_results if r.get("flag_vcp")),
    "rs": sum(1 for r in normalized_results if r.get("flag_rs_elite")),
    "stage2": sum(1 for r in normalized_results if r.get("flag_stage2")),
    "price_action": sum(1 for r in normalized_results if r.get("flag_price_action")),
    "fundamentals": sum(1 for r in normalized_results if r.get("flag_fund_strong")),
    "value_screen": sum(1 for r in normalized_results if r.get("flag_value_screen")),
    "quality_screen": sum(1 for r in normalized_results if r.get("flag_quality_screen")),
    "low_reversal": sum(1 for r in normalized_results if r.get("flag_low_reversal")),
    "delivery_spike": sum(1 for r in normalized_results if r.get("flag_delivery_spike")),
    "promoter_buy": sum(1 for r in normalized_results if r.get("flag_promoter_buying")),
    "bb_squeeze": sum(1 for r in normalized_results if r.get("flag_bb_squeeze")),
    "ipo_base": sum(1 for r in normalized_results if r.get("flag_ipo_base")),
    "dryup_pattern": sum(1 for r in normalized_results if r.get("flag_dryup_pattern")),
    "near_52w_high": sum(1 for r in normalized_results if r.get("flag_52w_breakout_zone")),
}

print(f"\n{'=' * 65}")
print(f"  ✅ SCAN COMPLETE — {elapsed:.0f}s elapsed")
print(f"  📁 Saved: {cache_file} ({file_size_mb:.1f} MB)")
print(f"  📊 Total stocks: {counts['all']}")
print(f"{'─' * 65}")
print(f"  Tab counts:")
for tab, count in counts.items():
    if tab != "all":
        print(f"    {tab:20s}: {count}")
print(f"{'=' * 65}")
print(f"\n  Next steps:")
print(f"    cd C:\\Users\\USER\\Downloads\\trade-stag-app")
print(f"    git add backend/scan_cache.json")
print(f"    git commit -m \"Scan data {datetime.now().strftime('%d %b %Y')}\"")
print(f"    git push")
print(f"\n  Render will auto-deploy and serve this data.\n")

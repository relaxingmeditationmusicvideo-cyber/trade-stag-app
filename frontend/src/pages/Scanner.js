import React, { useState, useMemo, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { formatPrice, formatPct, gradeBg } from '../App';

// ─── Scanner config: each scanner = filter + default sort + label ───
// Names are SEBI-neutral, inspired by StockMagnets naming conventions.
// Logic and filter parameters are UNCHANGED.
const SCANNERS = {
  all:           { name: 'All Stocks',           icon: '📊', filter: () => true,                                  sort: 'score', dir: 'desc' },
  aplus:         { name: '52 Week Leaders',      icon: '⭐', filter: r => r.flag_aplus,                            sort: 'score', dir: 'desc' },
  expert:        { name: 'Multi-Factor Score',   icon: '🎯', filter: r => r.flag_expert_pick,                     sort: 'expert_yes', dir: 'desc' },
  trade:         { name: 'High Grade Stocks',    icon: '💡', filter: r => r.flag_strong_grade && !r.pledge_danger, sort: 'confidence_pct', dir: 'desc' },
  breakouts:     { name: 'Breakout Scanner',     icon: '⚡', filter: r => r.flag_breakout,                        sort: 'score', dir: 'desc' },
  volsurge:      { name: 'Volume Breakout',      icon: '🔥', filter: r => r.flag_vol_surge,                       sort: 'vol_ratio', dir: 'desc' },
  accumulation:  { name: 'Accumulation Zone',    icon: '🏦', filter: r => r.flag_accumulation,                    sort: 'accum_score', dir: 'desc' },
  ema:           { name: 'Golden Crossover',     icon: '📈', filter: r => r.flag_ema_scanner,                     sort: 'score', dir: 'desc' },
  vcp:           { name: 'VCP Formation',        icon: '🔷', filter: r => r.flag_vcp,                             sort: 'vcp_score', dir: 'desc' },
  rs:            { name: 'RS Momentum',          icon: '🚀', filter: r => r.flag_rs_elite,                        sort: 'rs_percentile', dir: 'desc' },
  stage2:        { name: 'Stage 2 Uptrend',      icon: '✅', filter: r => r.flag_stage2,                          sort: 'score', dir: 'desc' },
  price_action:  { name: 'Price Action',         icon: '📉', filter: r => r.flag_price_action,                    sort: 'score', dir: 'desc' },
  fundamentals:  { name: 'Fundamental Score',    icon: '💎', filter: r => r.flag_fund_strong,                     sort: 'fund_score', dir: 'desc' },
  value_screen:  { name: 'Undervalued Growth',   icon: '💰', filter: r => r.flag_value_screen,                   sort: 'pe_ratio', dir: 'asc' },
  quality_screen:{ name: 'Quality & Blue Chips', icon: '🏆', filter: r => r.flag_quality_screen,                 sort: 'fund_score', dir: 'desc' },
};

// ─── Filter chips definition ───
const CHIPS = [
  { key: '', label: 'All' },
  { key: 'A+', label: 'A+', type: 'grade' },
  { key: 'A', label: 'A', type: 'grade' },
  { key: 'B+', label: 'B+', type: 'grade' },
  { sep: true },
  { key: 'nr7', label: 'NR7', test: r => r.flag_nr7 },
  { key: 'inside_day', label: 'Inside Day', test: r => r.flag_inside_day },
  { key: 'pocket_pivot', label: 'Pocket Pivot', test: r => r.flag_pocket_pivot },
  { key: 'vcp', label: '🔷 VCP', test: r => r.flag_vcp },
  { key: 'vol_dryup', label: '📉 Vol Dry-Up', test: r => r.flag_vol_dryup },
  { key: 'breakout', label: '⚡ Breakout', test: r => r.flag_breakout },
  { sep: true },
  { key: 'gainer', label: '📈 Gainers Today', test: r => r.flag_gainer },
  { key: 'loser', label: '📉 Losers Today', test: r => r.flag_loser },
  { key: 'gainer_5d', label: '📈 5D Gainer', test: r => r.flag_gainer_5d },
  { sep: true },
  { key: 'stage2', label: '✅ Stage 2', test: r => r.flag_stage2 },
  { key: 'fund_strong', label: '💎 Fund Strong', test: r => r.flag_fund_strong },
  { key: 'accumulation', label: '🏦 Accum', test: r => r.flag_accumulation },
  { key: 'rs_elite', label: '🚀 RS Elite', test: r => r.flag_rs_elite },
  { key: 'hi_delivery', label: '📦 Delivery>55%', test: r => r.flag_hi_delivery },
  { key: 'vol_surge', label: '🔥 Vol Surge', test: r => r.flag_vol_surge },
  { key: 'pledge_danger', label: '🚨 Pledge Danger', test: r => r.flag_pledge_danger },
  { key: 'earnings_warn', label: '⚠️ Near Results', test: r => r.flag_earnings_warn },
];

// ─── Sort buttons ───
const SORT_BUTTONS = [
  { label: 'Score ↓',     field: 'score',         dir: 'desc' },
  { label: '1D% ↓',       field: 'chg_1d',        dir: 'desc' },
  { label: '1D% ↑',       field: 'chg_1d',        dir: 'asc'  },
  { label: '5D% ↓',       field: 'chg_5d',        dir: 'desc' },
  { label: '1M% ↓',       field: 'chg_1m',        dir: 'desc' },
  { label: 'Vol Ratio ↓', field: 'vol_ratio',     dir: 'desc' },
  { label: 'BB Tight ↑',  field: 'bb_width',      dir: 'asc'  },
  { label: 'RS%ile ↓',    field: 'rs_percentile', dir: 'desc' },
];

// ─── Sparkline SVG ───
function Sparkline({ data, color }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 44, h = 16;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg className="sparkline" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Score breakdown tooltip ───
function ScoreCell({ score, top, color }) {
  const tip = top?.length ? top.map(t => `${t.name}:${Math.round(t.value)}`).join(' | ') : `Score: ${score}`;
  return (
    <div className="score-cell" title={tip}>
      <span className="score-num">{Math.round(score)}</span>
      <div className="prog-bar"><div className="prog-fill" style={{ width: `${Math.min(score,100)}%`, background: color }} /></div>
    </div>
  );
}

// ─── Stock row ───
function StockRow({ row, idx, onClick }) {
  const gradeColor = gradeBg(row.grade);
  const sparkColor = (row.chg_5d || 0) >= 0 ? '#10b981' : '#ef4444';
  const ts = row.trade_setup || {};

  return (
    <tr onClick={onClick} className="stock-row">
      <td className="muted">{idx + 1}</td>
      <td><strong>{row.symbol}</strong></td>
      <td><span className="grade-badge" style={{ background: gradeColor }}>{row.grade}</span></td>
      <td><ScoreCell score={row.score} top={row.score_top} color={gradeColor} /></td>
      <td className="price-cell">
        <div className="price-flex">
          <span>{formatPrice(row.price)}</span>
          <Sparkline data={row.sparkline} color={sparkColor} />
        </div>
      </td>
      <td className={row.chg_1d >= 0 ? 'up' : 'down'}>{formatPct(row.chg_1d)}</td>
      <td className={row.chg_5d >= 0 ? 'up' : 'down'}>{formatPct(row.chg_5d)}</td>
      <td className={row.chg_1m >= 0 ? 'up' : 'down'}>{formatPct(row.chg_1m)}</td>
      <td className={row.chg_3m >= 0 ? 'up' : 'down'}>{formatPct(row.chg_3m)}</td>
      <td style={{ color: (row.rsi || 0) >= 60 ? '#10b981' : (row.rsi || 0) >= 40 ? '#f59e0b' : '#ef4444' }}>{(row.rsi || 0).toFixed(1)}</td>
      <td style={{ color: (row.adx || 0) >= 25 ? '#10b981' : '#f59e0b' }}>{(row.adx || 0).toFixed(1)}</td>
      <td className="muted">{(row.bb_width || 0).toFixed(1)}%</td>
      <td>
        <div className="rs-cell">
          <div className="prog-bar small"><div className="prog-fill" style={{ width: `${row.rs_percentile || 0}%`, background: '#a78bfa' }} /></div>
          <span style={{ color: '#a78bfa' }}>{Math.round(row.rs_percentile || 0)}</span>
        </div>
      </td>
      <td style={{ color: (row.vol_ratio || 0) >= 1.5 ? '#10b981' : '#8892a4' }}>{(row.vol_ratio || 0).toFixed(2)}x</td>
      <td style={{ color: row.delivery_pct >= 55 ? '#10b981' : '#8892a4' }}>{row.delivery_pct ? `${Math.round(row.delivery_pct)}%` : '—'}</td>
      <td className="neutral">{row.pct_from_high ? `${row.pct_from_high.toFixed(1)}%` : '—'}</td>
      <td><span className={`stage-badge ${row.is_stage2 ? 'stage-2' : ''}`}>{row.stage?.includes('2') ? 'S2' : row.stage?.includes('1') ? 'S1' : row.stage?.[0] || '—'}</span></td>
      <td><span className="fund-badge">{row.fund_grade || 'N/A'}</span></td>
      <td className="muted">{row.pledge_pct != null ? `${row.pledge_pct.toFixed(1)}%` : '—'}</td>
      <td className="sector-cell muted">{row.sector}</td>
      <td className="trade-cell">
        {(ts.entry || 0) > 0 ? (
          <>
            <span className="trade-entry">₹{(ts.entry || 0).toFixed(1)}</span> /
            <span className="trade-sl"> ₹{(ts.stop_loss || ts.sl || 0).toFixed(1)}</span> /
            <span className="trade-t1"> ₹{(ts.target_1 || ts.target1 || ts.t1 || 0).toFixed(1)}</span>
          </>
        ) : '—'}
      </td>
      <td className="qty-cell">{ts.qty || '—'}</td>
      <td className="signals-cell">
        {(row.active_signals || []).slice(0, 5).map((s, i) => (
          <span key={i} className={`signal-tag ${s.includes('Elite') || s.includes('Strong Match') ? 'signal-elite' : ''}`}>
            {s.replace('CONVICTION', 'Strong Match').replace(/\bBUY\b/gi, 'Bullish Signal').replace(/\bSell\b/gi, 'Bearish Signal')}
          </span>
        ))}
      </td>
    </tr>
  );
}

export default function Scanner({ data, loading }) {
  const { scanner = 'all' } = useParams();
  const navigate = useNavigate();
  const cfg = SCANNERS[scanner] || SCANNERS.all;

  const [search, setSearch] = useState('');
  const [sectorFilter, setSectorFilter] = useState('');
  const [chipFilter, setChipFilter] = useState('');
  const [scoreMin, setScoreMin] = useState(0);
  const [sortField, setSortField] = useState(cfg.sort);
  const [sortDir, setSortDir] = useState(cfg.dir);

  // Reset filters when switching scanner
  useEffect(() => {
    setSortField(cfg.sort);
    setSortDir(cfg.dir);
    setChipFilter('');
    setScoreMin(0);
  }, [scanner, cfg.sort, cfg.dir]);

  const stocks = data?.stocks || [];

  // Build sector list from data
  const sectors = useMemo(() => {
    const set = new Set();
    stocks.forEach(s => s.sector && set.add(s.sector));
    return Array.from(set).sort();
  }, [stocks]);

  // Apply scanner + chip + search + score filters
  const filtered = useMemo(() => {
    let out = stocks.filter(cfg.filter);

    if (chipFilter) {
      const chip = CHIPS.find(c => c.key === chipFilter);
      if (chip) {
        if (chip.type === 'grade') out = out.filter(r => r.grade === chip.key);
        else if (chip.test) out = out.filter(chip.test);
      }
    }

    if (sectorFilter) out = out.filter(r => r.sector === sectorFilter);
    if (scoreMin > 0) out = out.filter(r => r.score >= scoreMin);
    if (search) {
      const q = search.toLowerCase();
      out = out.filter(r => r.symbol.toLowerCase().includes(q) || (r.sector || '').toLowerCase().includes(q));
    }

    // Sort
    const dir = sortDir === 'desc' ? -1 : 1;
    out = [...out].sort((a, b) => {
      const av = a[sortField] ?? 0;
      const bv = b[sortField] ?? 0;
      if (av < bv) return -1 * dir;
      if (av > bv) return  1 * dir;
      return 0;
    });

    return out;
  }, [stocks, cfg, chipFilter, sectorFilter, scoreMin, search, sortField, sortDir]);

  if (loading && !stocks.length) {
    return <div className="loading-card">⏳ Loading scan data...</div>;
  }

  return (
    <div className="scanner-page">
      {/* Screen Header */}
      <div className="screen-header">
        <div className="sh-icon">{cfg.icon}</div>
        <div className="sh-info">
          <div className="sh-title">{cfg.name}</div>
          <div className="sh-desc">Filtered from {stocks.length} stocks · {filtered.length} matches</div>
        </div>
        <div className="sh-count">{filtered.length}</div>
      </div>

      {/* Search + Sector + counter */}
      <div className="scanner-controls">
        <div className="search-bar">
          <span className="search-icon">🔍</span>
          <input type="text" placeholder="Search symbol or sector..." value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <select className="sector-select" value={sectorFilter} onChange={e => setSectorFilter(e.target.value)}>
          <option value="">All Sectors</option>
          {sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <span className="results-counter">{filtered.length} stocks</span>
      </div>

      {/* Sort buttons + score range */}
      <div className="sort-bar">
        <span className="sort-lbl">Sort:</span>
        {SORT_BUTTONS.map((b, i) => {
          const active = sortField === b.field && sortDir === b.dir;
          return (
            <button
              key={i}
              className={`sort-btn ${active ? 'active' : ''}`}
              onClick={() => { setSortField(b.field); setSortDir(b.dir); }}
            >{b.label}</button>
          );
        })}
        <div className="filter-sep" />
        <span className="range-filter">
          Score ≥ <input type="range" min="0" max="100" step="5" value={scoreMin} onChange={e => setScoreMin(+e.target.value)} />
          <span className="range-val">{scoreMin}</span>
        </span>
      </div>

      {/* Filter chips */}
      <div className="filter-row">
        <span className="filter-label">Filter:</span>
        {CHIPS.map((c, i) => c.sep ? (
          <div key={i} className="filter-sep" />
        ) : (
          <button
            key={i}
            className={`filter-btn ${chipFilter === c.key ? 'on' : ''}`}
            onClick={() => setChipFilter(chipFilter === c.key ? '' : c.key)}
          >{c.label}</button>
        ))}
      </div>

      {/* Table */}
      <div className="tbl-wrap">
        <table className="stock-table">
          <thead>
            <tr>
              <th>#</th><th>Symbol</th><th>Grade</th><th>Score</th><th>Price</th>
              <th>1D%</th><th>5D%</th><th>1M%</th><th>3M%</th>
              <th>RSI</th><th>ADX</th><th>BB%</th><th>RS%ile</th>
              <th>Vol Ratio</th><th>Delivery%</th><th>52W High%</th>
              <th>Stage</th><th>Fund</th><th>Pledge%</th><th>Sector</th>
              <th>Support / Risk / Res</th><th>Lot*</th><th>Signals</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((row, i) => (
              <StockRow key={row.symbol + i} row={row} idx={i} onClick={() => navigate(`/stock/${row.symbol}`)} />
            ))}
          </tbody>
        </table>
        {filtered.length > 200 && (
          <div className="more-rows">Showing first 200 of {filtered.length} matches</div>
        )}
        {filtered.length === 0 && (
          <div className="no-results">No stocks match these filters</div>
        )}
      </div>
    </div>
  );
}

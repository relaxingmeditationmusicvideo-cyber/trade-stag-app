import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { formatPct, gradeBg, num } from '../App';

function Dashboard({ data, loading }) {
  const stocks = data?.stocks || [];
  const counts = data?.counts || {};
  const pulse = data?.market_pulse || {};

  const stats = useMemo(() => {
    const grades = {};
    let adv = 0, dec = 0, unch = 0;
    let above200 = 0;
    stocks.forEach(s => {
      grades[s.grade] = (grades[s.grade] || 0) + 1;
      if (s.chg_1d > 0) adv++;
      else if (s.chg_1d < 0) dec++;
      else unch++;
      if (s.above_200ema) above200++;
    });
    const total = stocks.length || 1;
    return {
      grades, adv, dec, unch,
      above200pct: (above200 / total * 100).toFixed(1),
    };
  }, [stocks]);

  const fii = num(pulse?.fii_dii?.fii_net);
  const dii = num(pulse?.fii_dii?.dii_net);
  const fii5d = num(pulse?.fii_dii?.fii_5d);
  const pcr = num(pulse?.pcr?.nifty_pcr ?? pulse?.pcr);
  const wpcr = num(pulse?.pcr?.weekly_pcr);
  const maxPain = num(pulse?.max_pain?.value ?? pulse?.max_pain?.max_pain ?? pulse?.max_pain);
  const vix = num(pulse?.india_vix ?? stocks[0]?.india_vix);
  const weeklyExpiry = (typeof pulse?.pcr?.weekly_expiry === 'string') ? pulse.pcr.weekly_expiry : 'N/A';
  const pcrSent = (typeof pulse?.pcr?.sentiment === 'string') ? pulse.pcr.sentiment : '';

  if (loading && !stocks.length) {
    return <div className="loading-card">⏳ Loading market data...</div>;
  }

  if (!stocks.length) {
    return (
      <div className="empty-state">
        <h2>No scan data yet</h2>
        <p>Trigger a fresh scan from PowerShell:</p>
        <code>Invoke-WebRequest -Uri http://localhost:8000/api/scan -Method POST</code>
      </div>
    );
  }

  return (
    <>
      {/* Pulse Strip */}
      <div className="pulse-strip">
        <PulseCard label="Nifty PCR"      val={pcr != null ? pcr.toFixed(2) : 'N/A'}    sub={pcrSent}                           color="amber" />
        <PulseCard label="Weekly PCR"     val={wpcr != null ? wpcr.toFixed(2) : 'N/A'}  sub={`Exp ${weeklyExpiry}`}             color="red" />
        <PulseCard label="Max Pain"       val={maxPain != null ? Math.round(maxPain) : 'N/A'} sub="Nifty"                       color="amber" />
        <PulseCard label="FII 5-Day"      val={fii5d != null ? fii5d.toFixed(0) : 'N/A'} sub="Cr"                               color={(fii5d || 0) >= 0 ? 'green' : 'red'} />
        <PulseCard label="Market Breadth" val={`${stats.above200pct}%`}                  sub={`Above 200 EMA · ${stats.above200pct >= 60 ? 'STRONG' : stats.above200pct >= 40 ? 'OK' : 'WEAK'}`} color={stats.above200pct >= 60 ? 'green' : stats.above200pct >= 40 ? 'amber' : 'red'} />
        <PulseCard label="India VIX"      val={vix != null ? vix.toFixed(2) : 'N/A'}    sub="Fear gauge"                        color="amber" />
        <PulseCard label="FII Today"      val={fii != null ? `${fii >= 0 ? '+' : ''}${fii.toFixed(0)}` : 'N/A'} sub={`DII: ${dii != null ? (dii >= 0 ? '+' : '') + dii.toFixed(0) : 'N/A'}`} color={(fii || 0) >= 0 ? 'green' : 'red'} />
      </div>

      {/* Advance/Decline bar */}
      <div className="ad-bar">
        <div className="ad-adv" style={{ width: `${(stats.adv / stocks.length * 100).toFixed(1)}%` }}>{stats.adv}▲</div>
        <div className="ad-unch" style={{ width: `${(stats.unch / stocks.length * 100).toFixed(1)}%`, minWidth: 4 }} />
        <div className="ad-dec" style={{ width: `${(stats.dec / stocks.length * 100).toFixed(1)}%` }}>{stats.dec}▼</div>
      </div>

      {/* Stat grid */}
      <div className="stat-grid">
        <div className="stat-card"><div className="stat-label">Analyzed</div><div className="stat-val">{stocks.length}</div><div className="stat-sub">NSE 500</div></div>
        <div className="stat-card"><div className="stat-label">A+ / A Grade</div><div className="stat-val text-orange">{(stats.grades['A+'] || 0) + (stats.grades['A'] || 0)}</div><div className="stat-sub">Top graded</div></div>
        <div className="stat-card"><div className="stat-label">B+ Grade</div><div className="stat-val text-cyan">{stats.grades['B+'] || 0}</div><div className="stat-sub">Above average</div></div>
        <div className="stat-card"><div className="stat-label">Multi-Factor Score</div><div className="stat-val text-amber">{counts.expert || 0}</div><div className="stat-sub">13-pt checklist</div></div>
        <div className="stat-card"><div className="stat-label">Breakout Scanner</div><div className="stat-val text-orange">{counts.breakouts || 0}</div><div className="stat-sub">Active</div></div>
        <div className="stat-card"><div className="stat-label">Volume Breakout</div><div className="stat-val text-amber">{counts.volsurge || 0}</div><div className="stat-sub">Above avg</div></div>
        <div className="stat-card"><div className="stat-label">RS Momentum</div><div className="stat-val text-purple">{counts.rs || 0}</div><div className="stat-sub">{'>'}90 percentile</div></div>
        <div className="stat-card"><div className="stat-label">Stage 2 Uptrend</div><div className="stat-val text-cyan">{counts.stage2 || 0}</div><div className="stat-sub">Weinstein</div></div>
      </div>

      {/* Quick scanner cards */}
      <h3 className="section-h">Popular Screeners</h3>
      <div className="scanner-grid">
        {[
          { id: 'aplus',        name: '52 Week Leaders',      icon: '⭐', color: '#d4a024' },
          { id: 'expert',       name: 'Multi-Factor Score',   icon: '🎯', color: '#22d3ee' },
          { id: 'breakouts',    name: 'Breakout Scanner',     icon: '⚡', color: '#fbbf24' },
          { id: 'volsurge',     name: 'Volume Breakout',      icon: '🔥', color: '#ef4444' },
          { id: 'vcp',          name: 'VCP Formation',        icon: '🔷', color: '#06b6d4' },
          { id: 'rs',           name: 'RS Momentum',          icon: '🚀', color: '#a78bfa' },
          { id: 'stage2',       name: 'Stage 2 Uptrend',      icon: '✅', color: '#10b981' },
          { id: 'ema',          name: 'Golden Crossover',     icon: '📈', color: '#84cc16' },
        ].map(s => (
          <Link to={`/app/scanner/${s.id}`} className="scanner-card" key={s.id}>
            <div className="sc-icon" style={{ color: s.color }}>{s.icon}</div>
            <div className="sc-info">
              <div className="sc-name">{s.name}</div>
              <div className="sc-count">{counts[s.id] || 0} stocks</div>
            </div>
            <div className="sc-arrow">→</div>
          </Link>
        ))}
      </div>

      {/* Grade distribution */}
      <h3 className="section-h">Grade Distribution</h3>
      <div className="grade-bars">
        {['A+', 'A', 'B+', 'B', 'C', 'D'].map(g => {
          const cnt = stats.grades[g] || 0;
          const pct = stocks.length ? (cnt / stocks.length * 100) : 0;
          return (
            <div key={g} className="grade-bar-row">
              <span className="grade-label" style={{ background: gradeBg(g) }}>{g}</span>
              <div className="grade-bar"><div className="grade-bar-fill" style={{ width: `${pct}%`, background: gradeBg(g) }} /></div>
              <span className="grade-bar-count">{cnt} <span className="muted">({pct.toFixed(1)}%)</span></span>
            </div>
          );
        })}
      </div>

      {/* Top 10 by score */}
      <h3 className="section-h">Top 10 by Score</h3>
      <div className="top10-list">
        {[...stocks].sort((a, b) => b.score - a.score).slice(0, 10).map((s, i) => (
          <Link to={`/stock/${s.symbol}`} key={s.symbol} className="top10-row">
            <span className="top10-rank">#{i + 1}</span>
            <span className="grade-badge" style={{ background: gradeBg(s.grade) }}>{s.grade}</span>
            <span className="top10-sym"><strong>{s.symbol}</strong></span>
            <span className="muted top10-sec">{s.sector}</span>
            <span className="top10-score">{Math.round(s.score)}</span>
            <span className={s.chg_1d >= 0 ? 'up' : 'down'}>{formatPct(s.chg_1d)}</span>
          </Link>
        ))}
      </div>
    </>
  );
}

function PulseCard({ label, val, sub, color }) {
  const colorMap = { green: '#10b981', red: '#ef4444', amber: '#f59e0b', cyan: '#22d3ee' };
  return (
    <div className="pulse-card">
      <div className="pc-label">{label}</div>
      <div className="pc-val" style={{ color: colorMap[color] || '#e8ecf4' }}>{val}</div>
      <div className="pc-sub">{sub}</div>
    </div>
  );
}

export default Dashboard;

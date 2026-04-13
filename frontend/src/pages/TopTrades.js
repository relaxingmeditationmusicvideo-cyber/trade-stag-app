import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatNum, formatPct, gradeClass, getScoreColor } from '../App';

function TopTrades({ api }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [capital, setCapital] = useState(500000);

  useEffect(() => {
    fetch(`${api}/api/top-trades?capital=${capital}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [api, capital]);

  if (loading) return <div className="loading-spinner">Loading top trades...</div>;

  const trades = data?.trades || [];

  return (
    <div>
      <h1 className="page-title">Top Scoring Setups</h1>
      <p className="page-subtitle">Highest-scoring setups ranked by multi-factor analysis with position sizing</p>

      {/* Capital Input */}
      <div className="filter-bar mb-6">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted">Trading Capital:</span>
          <input
            type="number"
            value={capital}
            onChange={e => setCapital(Number(e.target.value))}
            style={{ width: 160 }}
          />
          <span className="text-sm text-muted">Risk: {data?.risk_pct}% per trade</span>
        </div>
      </div>

      {/* Trade Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {trades.map((trade, idx) => {
          const ts = trade.trade_setup || {};
          return (
            <div
              key={trade.symbol}
              className="card"
              style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
              onClick={() => navigate(`/stock/${trade.symbol}`)}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--cyan)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-4">
                  <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--muted)', width: 32 }}>#{idx + 1}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span style={{ fontSize: 18, fontWeight: 700 }}>{trade.symbol}</span>
                      <span className={`grade ${gradeClass(trade.grade)}`}>{trade.grade}</span>
                      <span className={`signal-tag ${trade.expert_decision === 'CONVICTION' ? 'bullish' : ''}`}>
                        {trade.expert_decision}
                      </span>
                    </div>
                    <div className="text-xs text-muted">{trade.name} — {trade.sector}</div>
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{formatNum(trade.price)}</div>
                  <div className={trade.chg_1d >= 0 ? 'up' : 'down'}>{formatPct(trade.chg_1d)}</div>
                </div>
              </div>

              {/* Trade details grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 8 }}>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Score</div>
                  <div className="font-bold" style={{ color: getScoreColor(trade.score) }}>{trade.score}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Confidence</div>
                  <div className="font-bold text-cyan">{trade.confidence_pct}%</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Entry</div>
                  <div className="font-bold text-cyan">{formatNum(ts.entry)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Stop Loss</div>
                  <div className="font-bold text-red">{formatNum(ts.stop_loss)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Target 1</div>
                  <div className="font-bold text-green">{formatNum(ts.target1)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Qty</div>
                  <div className="font-bold">{trade.position_qty}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">R:R</div>
                  <div className="font-bold" style={{ color: ts.rr_ratio >= 2 ? 'var(--green)' : 'var(--amber)' }}>
                    1:{ts.rr_ratio?.toFixed(1)}
                  </div>
                </div>
              </div>

              {/* Signals */}
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(trade.active_signals || []).slice(0, 5).map((sig, i) => (
                  <span key={i} className={`signal-tag ${
                    sig.includes('BUY') || sig.includes('Breakout') || sig.includes('Bullish') ? 'bullish' :
                    sig.includes('Sell') || sig.includes('Death') ? 'bearish' : ''
                  }`}>
                    {sig.replace(/[🔥🟢✅📈📋🚨💀🌟🕯📶🎯⚡⚠️]/g, '').trim()}
                  </span>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TopTrades;

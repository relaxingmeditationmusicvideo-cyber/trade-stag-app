import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatNum, formatPct, gradeClass, getScoreColor } from '../App';

function TopTrades({ api }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetch(`${api}/api/top-trades`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [api]);

  if (loading) return <div className="loading-spinner">Loading top scored stocks...</div>;

  const trades = data?.trades || [];

  return (
    <div>
      <h1 className="page-title">Top Scored Stocks</h1>
      <p className="page-subtitle">Stocks ranked by automated multi-factor screening score</p>

      {/* Illustrative disclaimer */}
      <div className="compliance-notice" style={{
        background: 'rgba(212,160,36,0.08)',
        border: '1px solid rgba(212,160,36,0.25)',
        borderRadius: 8,
        padding: '10px 16px',
        marginBottom: 16,
        fontSize: 11,
        color: 'var(--muted)',
        lineHeight: 1.5
      }}>
        <strong style={{ color: 'var(--amber)' }}>Illustrative only:</strong> The technical levels shown below
        (support, resistance, ATR-based ranges) are auto-calculated from historical price data and are NOT
        buy/sell recommendations. Always do your own research and consult a SEBI-registered adviser before
        making any investment decision.
      </div>

      {/* Stock Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {trades.map((trade, idx) => {
          const ts = trade.trade_setup || {};
          /* Map advisory language to neutral screening terms */
          const decisionLabel = (trade.expert_decision || '')
            .replace('CONVICTION', 'High Score')
            .replace('TRADE', 'Score Match')
            .replace('SKIP', 'Low Score')
            .replace('BUY', 'Bullish Pattern')
            .replace('SELL', 'Bearish Pattern');
          return (
            <div
              key={trade.symbol}
              className="card"
              style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
              onClick={() => navigate(`/app/stock/${trade.symbol}`)}
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
                      {decisionLabel && (
                        <span className="signal-tag">{decisionLabel}</span>
                      )}
                    </div>
                    <div className="text-xs text-muted">{trade.name} — {trade.sector}</div>
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 22, fontWeight: 700 }}>{formatNum(trade.price)}</div>
                  <div className={trade.chg_1d >= 0 ? 'up' : 'down'}>{formatPct(trade.chg_1d)}</div>
                </div>
              </div>

              {/* Technical data grid — illustrative levels */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Score</div>
                  <div className="font-bold" style={{ color: getScoreColor(trade.score) }}>{trade.score}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Match %</div>
                  <div className="font-bold text-cyan">{trade.confidence_pct}%</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Near Support</div>
                  <div className="font-bold text-cyan">{formatNum(ts.entry)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">ATR Risk</div>
                  <div className="font-bold text-red">{formatNum(ts.stop_loss)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Resistance</div>
                  <div className="font-bold text-green">{formatNum(ts.target1)}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '8px 4px', background: 'var(--bg4)', borderRadius: 6 }}>
                  <div className="text-xs text-muted">Range Ratio</div>
                  <div className="font-bold" style={{ color: ts.rr_ratio >= 2 ? 'var(--green)' : 'var(--amber)' }}>
                    1:{ts.rr_ratio?.toFixed(1)}
                  </div>
                </div>
              </div>

              {/* Signals — neutral pattern language */}
              <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(trade.active_signals || []).slice(0, 5).map((sig, i) => {
                  /* Rewrite BUY/Sell to neutral pattern detection language */
                  const cleanSig = sig
                    .replace(/[🔥🟢✅📈📋🚨💀🌟🕯📶🎯⚡⚠️]/g, '')
                    .replace(/\bBUY\b/gi, 'Bullish Pattern')
                    .replace(/\bSell\b/gi, 'Bearish Pattern')
                    .trim();
                  const cls = cleanSig.includes('Bullish') || cleanSig.includes('Breakout') ? 'bullish' :
                              cleanSig.includes('Bearish') || cleanSig.includes('Death') ? 'bearish' : '';
                  return (
                    <span key={i} className={`signal-tag ${cls}`}>{cleanSig}</span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default TopTrades;

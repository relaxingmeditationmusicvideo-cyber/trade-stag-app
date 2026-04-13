import React, { useState, useEffect } from 'react';

function Sectors({ api }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('cards'); // 'cards' or 'table'

  useEffect(() => {
    fetch(`${api}/api/sectors`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [api]);

  if (loading) return <div className="loading-spinner">Loading sector data...</div>;

  const sectors = data?.sectors || [];

  const getStrengthColor = (s) => {
    if (s >= 70) return 'var(--green)';
    if (s >= 55) return 'var(--cyan)';
    if (s >= 40) return 'var(--amber)';
    return 'var(--red)';
  };

  const getStrengthLabel = (s) => {
    if (s >= 70) return 'Strong';
    if (s >= 55) return 'Moderate';
    if (s >= 40) return 'Weak';
    return 'Bearish';
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="page-title">Sector Momentum</h1>
          <p className="page-subtitle">Sector rankings by strength, RS alpha, and Stage 2 concentration</p>
        </div>
        <div className="flex gap-2">
          <button className={`btn ${view === 'cards' ? 'btn-primary' : 'btn-outline'}`} onClick={() => setView('cards')}>
            Cards
          </button>
          <button className={`btn ${view === 'table' ? 'btn-primary' : 'btn-outline'}`} onClick={() => setView('table')}>
            Table
          </button>
        </div>
      </div>

      {view === 'cards' ? (
        <div className="grid-3 mb-6">
          {sectors.map((sec, idx) => (
            <div key={sec.name} className="sector-card">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <div className="sector-name">{sec.name}</div>
                  <div className="text-xs text-muted">{sec.count} stocks</div>
                </div>
                <span style={{
                  fontSize: 12, fontWeight: 700, padding: '3px 10px',
                  borderRadius: 20,
                  background: `${getStrengthColor(sec.strength)}20`,
                  color: getStrengthColor(sec.strength)
                }}>
                  #{idx + 1}
                </span>
              </div>

              <div className="sector-strength" style={{ color: getStrengthColor(sec.strength) }}>
                {sec.strength?.toFixed(1)}
              </div>
              <div className="text-xs text-muted" style={{ marginBottom: 12 }}>
                Strength Score — {getStrengthLabel(sec.strength)}
              </div>

              <div className="score-bar" style={{ marginBottom: 12 }}>
                <div className="fill" style={{
                  width: `${sec.strength}%`,
                  background: getStrengthColor(sec.strength)
                }} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ padding: 8, background: 'var(--bg4)', borderRadius: 6, textAlign: 'center' }}>
                  <div className="text-xs text-muted">Avg RS</div>
                  <div className="font-bold text-sm" style={{ color: sec.avg_rs >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {sec.avg_rs >= 0 ? '+' : ''}{sec.avg_rs?.toFixed(1)}
                  </div>
                </div>
                <div style={{ padding: 8, background: 'var(--bg4)', borderRadius: 6, textAlign: 'center' }}>
                  <div className="text-xs text-muted">Stage 2</div>
                  <div className="font-bold text-sm text-cyan">{sec.stage2_count}</div>
                </div>
                <div style={{ padding: 8, background: 'var(--bg4)', borderRadius: 6, textAlign: 'center' }}>
                  <div className="text-xs text-muted">>200 EMA</div>
                  <div className="font-bold text-sm" style={{ color: sec.pct_above_200 >= 60 ? 'var(--green)' : 'var(--amber)' }}>
                    {sec.pct_above_200?.toFixed(0)}%
                  </div>
                </div>
                <div style={{ padding: 8, background: 'var(--bg4)', borderRadius: 6, textAlign: 'center' }}>
                  <div className="text-xs text-muted">Avg ADX</div>
                  <div className="font-bold text-sm" style={{ color: sec.avg_adx >= 25 ? 'var(--green)' : 'var(--muted)' }}>
                    {sec.avg_adx?.toFixed(1)}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ borderRadius: 12, border: '1px solid var(--border)', overflow: 'hidden' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Sector</th>
                <th>Strength</th>
                <th>Avg RS Alpha</th>
                <th>Stocks</th>
                <th>Stage 2</th>
                <th>% Above 200 EMA</th>
                <th>Avg ADX</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map((sec, idx) => (
                <tr key={sec.name}>
                  <td className="text-muted font-bold">{idx + 1}</td>
                  <td className="font-bold">{sec.name}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <span className="font-bold" style={{ color: getStrengthColor(sec.strength) }}>
                        {sec.strength?.toFixed(1)}
                      </span>
                      <div className="score-bar" style={{ width: 60 }}>
                        <div className="fill" style={{
                          width: `${sec.strength}%`,
                          background: getStrengthColor(sec.strength)
                        }} />
                      </div>
                    </div>
                  </td>
                  <td style={{ color: sec.avg_rs >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {sec.avg_rs >= 0 ? '+' : ''}{sec.avg_rs?.toFixed(2)}
                  </td>
                  <td>{sec.count}</td>
                  <td className="text-cyan font-bold">{sec.stage2_count}</td>
                  <td>
                    <span style={{ color: sec.pct_above_200 >= 60 ? 'var(--green)' : 'var(--amber)' }}>
                      {sec.pct_above_200?.toFixed(1)}%
                    </span>
                  </td>
                  <td>
                    <span style={{ color: sec.avg_adx >= 25 ? 'var(--green)' : 'var(--muted)' }}>
                      {sec.avg_adx?.toFixed(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default Sectors;

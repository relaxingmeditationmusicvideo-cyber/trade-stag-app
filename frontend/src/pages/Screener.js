import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatNum, formatPct, gradeClass, getScoreColor } from '../App';

function Screener({ api }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    grade: '', sector: '', min_score: '', signal: '',
    sort_by: 'score', sort_dir: 'desc',
  });
  const [search, setSearch] = useState('');

  const fetchData = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    params.set('page', page);
    params.set('page_size', 50);
    if (filters.grade) params.set('grade', filters.grade);
    if (filters.sector) params.set('sector', filters.sector);
    if (filters.min_score) params.set('min_score', filters.min_score);
    if (filters.signal) params.set('signal', filters.signal);
    params.set('sort_by', filters.sort_by);
    params.set('sort_dir', filters.sort_dir);

    fetch(`${api}/api/screener?${params}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [api, page, filters]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSort = (field) => {
    setFilters(prev => ({
      ...prev,
      sort_by: field,
      sort_dir: prev.sort_by === field && prev.sort_dir === 'desc' ? 'asc' : 'desc',
    }));
    setPage(1);
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const sortIcon = (field) => {
    if (filters.sort_by !== field) return '↕';
    return filters.sort_dir === 'desc' ? '↓' : '↑';
  };

  const results = data?.results || [];
  const filtered = search
    ? results.filter(r => r.symbol.includes(search.toUpperCase()) || (r.name || '').toUpperCase().includes(search.toUpperCase()))
    : results;

  const sectors = [...new Set(results.map(r => r.sector).filter(Boolean))].sort();
  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="page-title">Stock Screener</h1>
          <p className="page-subtitle">
            Filter NSE 500 stocks by grade, score, signals & technicals
            {data && <span> — Showing {data.total} stocks</span>}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="search-box">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
          <input
            placeholder="Search symbol or company..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <select value={filters.grade} onChange={e => handleFilterChange('grade', e.target.value)}>
          <option value="">All Grades</option>
          {['A+', 'A', 'B+', 'B', 'C', 'D'].map(g => <option key={g} value={g}>{g}</option>)}
        </select>

        <select value={filters.sector} onChange={e => handleFilterChange('sector', e.target.value)}>
          <option value="">All Sectors</option>
          {sectors.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select value={filters.min_score || ''} onChange={e => handleFilterChange('min_score', e.target.value)}>
          <option value="">Min Score</option>
          <option value="80">80+</option>
          <option value="60">60+</option>
          <option value="40">40+</option>
        </select>

        <select value={filters.signal} onChange={e => handleFilterChange('signal', e.target.value)}>
          <option value="">All Signals</option>
          <option value="supertrend">Supertrend BUY</option>
          <option value="breakout">Breakout</option>
          <option value="goldencross">Golden Cross</option>
          <option value="nr7">NR7</option>
          <option value="vcp">VCP</option>
          <option value="flatbase">Flat Base</option>
          <option value="bulkbuy">Bulk Buy</option>
        </select>
      </div>

      {/* Results Table */}
      {loading ? (
        <div className="loading-spinner">Loading screener data...</div>
      ) : (
        <>
          <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid var(--border)' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th onClick={() => handleSort('symbol')}>Symbol {sortIcon('symbol')}</th>
                  <th>Sector</th>
                  <th onClick={() => handleSort('grade')}>Grade {sortIcon('grade')}</th>
                  <th onClick={() => handleSort('score')}>Score {sortIcon('score')}</th>
                  <th onClick={() => handleSort('price')}>Price {sortIcon('price')}</th>
                  <th onClick={() => handleSort('chg_1d')}>1D % {sortIcon('chg_1d')}</th>
                  <th onClick={() => handleSort('chg_5d')}>5D % {sortIcon('chg_5d')}</th>
                  <th onClick={() => handleSort('chg_1m')}>1M % {sortIcon('chg_1m')}</th>
                  <th onClick={() => handleSort('rsi')}>RSI {sortIcon('rsi')}</th>
                  <th onClick={() => handleSort('delivery_pct')}>Delivery% {sortIcon('delivery_pct')}</th>
                  <th onClick={() => handleSort('vol_ratio')}>Vol Ratio {sortIcon('vol_ratio')}</th>
                  <th>Signals</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(stock => (
                  <tr key={stock.symbol} onClick={() => navigate(`/stock/${stock.symbol}`)} style={{ cursor: 'pointer' }}>
                    <td>
                      <div style={{ fontWeight: 700 }}>{stock.symbol}</div>
                      <div className="text-xs text-muted">{stock.name}</div>
                    </td>
                    <td className="text-xs text-muted">{stock.sector}</td>
                    <td>
                      <span className={`grade ${gradeClass(stock.grade)}`}>{stock.grade}</span>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="font-bold" style={{ color: getScoreColor(stock.score) }}>
                          {stock.score}
                        </span>
                        <div className="score-bar" style={{ width: 40 }}>
                          <div className="fill" style={{
                            width: `${stock.score}%`,
                            background: getScoreColor(stock.score)
                          }} />
                        </div>
                      </div>
                    </td>
                    <td className="font-mono">{formatNum(stock.price)}</td>
                    <td className={stock.chg_1d >= 0 ? 'up' : 'down'}>{formatPct(stock.chg_1d)}</td>
                    <td className={stock.chg_5d >= 0 ? 'up' : 'down'}>{formatPct(stock.chg_5d)}</td>
                    <td className={stock.chg_1m >= 0 ? 'up' : 'down'}>{formatPct(stock.chg_1m)}</td>
                    <td>
                      <span style={{
                        color: stock.rsi >= 50 && stock.rsi <= 68 ? 'var(--green)' :
                               stock.rsi > 70 ? 'var(--red)' : 'var(--amber)'
                      }}>
                        {stock.rsi?.toFixed(1)}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        color: stock.delivery_pct >= 55 ? 'var(--green)' :
                               stock.delivery_pct >= 40 ? 'var(--amber)' : 'var(--muted)'
                      }}>
                        {stock.delivery_pct?.toFixed(1)}%
                      </span>
                    </td>
                    <td>
                      <span style={{
                        color: stock.vol_ratio >= 1.5 ? 'var(--green)' :
                               stock.vol_ratio >= 1.0 ? 'var(--text)' : 'var(--muted)'
                      }}>
                        {stock.vol_ratio?.toFixed(2)}x
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, maxWidth: 200 }}>
                        {(stock.active_signals || []).slice(0, 3).map((sig, i) => (
                          <span key={i} className={`signal-tag ${
                            sig.includes('BUY') || sig.includes('Cross') || sig.includes('Breakout') ? 'bullish' :
                            sig.includes('Sell') || sig.includes('Death') ? 'bearish' : ''
                          }`}>
                            {sig.replace(/[🔥🟢✅📈📋🚨💀🌟🕯📶🎯⚡⚠️]/g, '').trim()}
                          </span>
                        ))}
                        {(stock.active_signals || []).length > 3 && (
                          <span className="signal-tag neutral">+{stock.active_signals.length - 3}</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="pagination">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>
              ← Prev
            </button>
            <span className="page-info">Page {page} of {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default Screener;

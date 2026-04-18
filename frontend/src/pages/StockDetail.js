import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { formatNum, formatPct, gradeClass, getScoreColor } from '../App';

const EXPERT_LABELS = {
  a1_nifty_above_dma: 'Nifty above 20 & 50 DMA',
  a2_breadth_supportive: 'Market breadth >= 55% above 200 EMA',
  b1_sector_strong: 'Sector strength >= 55',
  b2_sector_peers_breaking: 'Sector peers in breakout zone',
  c1_base_consolidation: '3-6 week consolidation / base formed',
  c2_price_structure_ok: 'Higher lows / tight range',
  d1_breakout_confirmed: 'Price at or above resistance',
  d2_candle_quality_ok: 'Strong candle — high delivery',
  e1_volume_surge: 'Breakout volume >= 1.5x average',
  e2_volume_contraction: 'Volume contraction after surge',
  f1_indicators_aligned: 'RSI 52-68, ADX >= 20, Supertrend Bullish',
  g1_stoploss_defined: 'ATR risk level defined, risk <= 7%',
  g2_rr_minimum: 'Risk : Reward >= 1:2',
};

const SCORE_LABELS = {
  delivery: { label: 'Delivery %', max: 12, icon: '📦' },
  fii_dii: { label: 'FII/DII Flow', max: 6, icon: '🌐' },
  bulk_deal: { label: 'Bulk/Block Deals', max: 12, icon: '📋' },
  promoter: { label: 'Promoter Activity', max: 10, icon: '👔' },
  vix: { label: 'India VIX', max: 8, icon: '📊' },
  oi_buildup: { label: 'OI Buildup', max: 10, icon: '📈' },
  pcr: { label: 'PCR Signal', max: 6, icon: '📉' },
  compression: { label: 'Compression', max: 14, icon: '🔄' },
  vol_dryup: { label: 'Volume Dry-up', max: 8, icon: '🏜️' },
  base_position: { label: 'Base Position', max: 8, icon: '🏗️' },
  supertrend: { label: 'Supertrend', max: 10, icon: '📡' },
  ema_alignment: { label: 'EMA Alignment', max: 6, icon: '📏' },
  rsi: { label: 'RSI', max: 9, icon: '📐' },
  adx: { label: 'ADX Trend', max: 8, icon: '💪' },
  weekly_trend: { label: 'Weekly Trend', max: 6, icon: '📅' },
  golden_cross: { label: 'Golden Cross', max: 8, icon: '✨' },
  freshness: { label: 'Freshness', max: 0, icon: '⏰' },
};

function StockDetail({ api }) {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const [stock, setStock] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');

  useEffect(() => {
    fetch(`${api}/api/stock/${symbol}`)
      .then(r => { if (!r.ok) throw new Error('Not found'); return r.json(); })
      .then(d => { setStock(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [api, symbol]);

  if (loading) return <div className="loading-spinner">Loading stock analysis...</div>;
  if (!stock) return (
    <div>
      <div className="back-btn" onClick={() => navigate(-1)}>← Back</div>
      <p className="text-muted">Stock {symbol} not found in latest scan.</p>
    </div>
  );

  const ts = stock.trade_setup || {};
  const checks = stock.expert_checks || {};
  const breakdown = stock.score_breakdown || {};
  const promo = stock.promoter_data || {};

  return (
    <div>
      <div className="back-btn" onClick={() => navigate(-1)}>← Back to Screener</div>

      {/* Header */}
      <div className="stock-detail-header">
        <div>
          <div className="flex items-center gap-4">
            <span className="stock-symbol-large">{stock.symbol}</span>
            <span className={`grade ${gradeClass(stock.grade)}`} style={{ fontSize: 16, width: 'auto', padding: '4px 12px', height: 'auto' }}>
              {stock.grade}
            </span>
            {stock.is_fno && <span className="signal-tag">F&O</span>}
            <span className={`signal-tag ${stock.expert_decision === 'CONVICTION' ? 'bullish' : stock.expert_decision === 'TRADE' ? '' : 'bearish'}`}>
              {(stock.expert_decision || '').replace('CONVICTION', 'Strong Match').replace('TRADE', 'Match')}
            </span>
          </div>
          <div className="text-sm text-muted" style={{ marginTop: 4 }}>
            {stock.name} — {stock.sector} — {stock.stage}
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div className="stock-price-large">{formatNum(stock.price)}</div>
          <div className={stock.chg_1d >= 0 ? 'up' : 'down'} style={{ fontSize: 16 }}>
            {formatPct(stock.chg_1d)} today
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {[
          { id: 'overview', label: 'Overview' },
          { id: 'expert', label: 'Checklist' },
          { id: 'trade', label: 'Tech Levels' },
          { id: 'institutional', label: 'Institutional' },
          { id: 'breakdown', label: 'Breakdown' },
        ].map(t => (
          <div key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </div>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div>
          {/* Score + Key Metrics */}
          <div className="grid-4 mb-6">
            <div className="kpi-card">
              <div className="kpi-label">Composite Score</div>
              <div className="kpi-value" style={{ color: getScoreColor(stock.score) }}>{stock.score}/100</div>
              <div className="score-bar" style={{ marginTop: 8 }}>
                <div className="fill" style={{ width: `${stock.score}%`, background: getScoreColor(stock.score) }} />
              </div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Criteria Met</div>
              <div className="kpi-value" style={{ color: getScoreColor(stock.confidence_pct) }}>{stock.confidence_pct}%</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">RS Alpha</div>
              <div className="kpi-value" style={{ color: stock.rs_alpha >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {stock.rs_alpha >= 0 ? '+' : ''}{stock.rs_alpha?.toFixed(2)}
              </div>
              <div className="text-xs text-muted">Percentile: {stock.rs_percentile}th</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">Expert Check</div>
              <div className="kpi-value" style={{ color: stock.expert_yes >= 10 ? 'var(--green)' : stock.expert_yes >= 7 ? 'var(--cyan)' : 'var(--red)' }}>
                {stock.expert_yes}/13
              </div>
              <div className="text-xs text-muted">{stock.expert_decision}</div>
            </div>
          </div>

          {/* Price Changes */}
          <div className="card mb-6">
            <div className="card-title">Price Performance</div>
            <div className="grid-4">
              {[['1 Day', stock.chg_1d], ['5 Days', stock.chg_5d], ['1 Month', stock.chg_1m], ['3 Months', stock.chg_3m]].map(([label, val]) => (
                <div key={label} style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                  <div className="text-xs text-muted" style={{ marginBottom: 4 }}>{label}</div>
                  <div className={`font-bold ${val >= 0 ? 'up' : 'down'}`} style={{ fontSize: 18 }}>
                    {formatPct(val)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Technicals Row */}
          <div className="grid-3 mb-6">
            <div className="card">
              <div className="card-title">Technicals</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  ['RSI', stock.rsi?.toFixed(1), stock.rsi >= 50 && stock.rsi <= 68 ? 'var(--green)' : 'var(--amber)'],
                  ['ADX', stock.adx?.toFixed(1), stock.adx >= 25 ? 'var(--green)' : 'var(--muted)'],
                  ['Delivery %', stock.delivery_pct?.toFixed(1) + '%', stock.delivery_pct >= 55 ? 'var(--green)' : 'var(--muted)'],
                  ['Vol Ratio', stock.vol_ratio?.toFixed(2) + 'x', stock.vol_ratio >= 1.5 ? 'var(--green)' : 'var(--muted)'],
                  ['BB Width', stock.bb_width?.toFixed(1), stock.bb_width < 8 ? 'var(--cyan)' : 'var(--muted)'],
                  ['% from 52W High', formatPct(stock.pct_from_high), stock.pct_from_high >= -5 ? 'var(--green)' : 'var(--muted)'],
                ].map(([label, val, color]) => (
                  <div key={label} className="flex items-center justify-between" style={{ fontSize: 13 }}>
                    <span className="text-muted">{label}</span>
                    <span style={{ fontWeight: 600, color }}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-title">EMA Levels</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  ['EMA 21', stock.ema_21],
                  ['EMA 50', stock.ema_50],
                  ['EMA 200', stock.ema_200],
                ].map(([label, val]) => {
                  const aboveBelow = stock.price > val;
                  return (
                    <div key={label} className="flex items-center justify-between" style={{ fontSize: 13 }}>
                      <span className="text-muted">{label}</span>
                      <span>
                        <span className="font-mono">{formatNum(val)}</span>
                        <span style={{ marginLeft: 8, fontSize: 11, color: aboveBelow ? 'var(--green)' : 'var(--red)' }}>
                          {aboveBelow ? 'Above' : 'Below'}
                        </span>
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="card">
              <div className="card-title">Active Signals</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {(stock.active_signals || []).map((sig, i) => {
                  const cleanSig = sig
                    .replace(/[🔥🟢✅📈📋🚨💀🌟🕯📶🎯⚡⚠️]/g, '')
                    .replace(/\bBUY\b/gi, 'Bullish Signal')
                    .replace(/\bSell\b/gi, 'Bearish Signal')
                    .trim();
                  return (
                    <span key={i} className={`signal-tag ${
                      cleanSig.includes('Bullish') || cleanSig.includes('Cross') || cleanSig.includes('Breakout') ? 'bullish' :
                      cleanSig.includes('Bearish') || cleanSig.includes('Death') || cleanSig.includes('Risk') ? 'bearish' : ''
                    }`} style={{ fontSize: 11, padding: '3px 8px' }}>
                      {cleanSig}
                    </span>
                  );
                })}
                {(!stock.active_signals || stock.active_signals.length === 0) && (
                  <span className="text-muted text-sm">No active signals detected</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Expert Checklist Tab */}
      {tab === 'expert' && (
        <div className="card">
          <div className="card-title">13-Point Expert Decision Checklist</div>
          <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--bg4)', borderRadius: 8 }}>
            <div className="flex items-center justify-between">
              <div>
                <span className="font-bold" style={{
                  color: stock.expert_yes >= 10 ? 'var(--green)' : stock.expert_yes >= 7 ? 'var(--cyan)' : 'var(--red)',
                  fontSize: 20
                }}>
                  {stock.expert_yes}/13 YES
                </span>
                <span className="text-muted" style={{ marginLeft: 12 }}>
                  {stock.expert_yes >= 10 ? 'STRONG MATCH — Most criteria met' :
                   stock.expert_yes >= 7 ? 'MODERATE MATCH — Above average criteria' :
                   'WEAK MATCH — Few criteria met'}
                </span>
              </div>
              <span className={`grade ${gradeClass(stock.grade)}`} style={{ fontSize: 16, width: 'auto', padding: '4px 16px', height: 'auto' }}>
                {(stock.expert_decision || '').replace('CONVICTION', 'Strong Match').replace('TRADE', 'Match')}
              </span>
            </div>
          </div>

          <div>
            {Object.entries(EXPERT_LABELS).map(([key, label]) => {
              const passed = checks[key];
              const category = key.split('_')[0];
              const categoryLabels = {
                a1: 'A. Market Context', a2: 'A. Market Context',
                b1: 'B. Sector', b2: 'B. Sector',
                c1: 'C. Price Structure', c2: 'C. Price Structure',
                d1: 'D. Breakout Quality', d2: 'D. Breakout Quality',
                e1: 'E. Volume', e2: 'E. Volume',
                f1: 'F. Indicators',
                g1: 'G. Risk Setup', g2: 'G. Risk Setup',
              };

              return (
                <div key={key} className="checklist-item">
                  <div className={`check-icon ${passed ? 'yes' : 'no'}`}>
                    {passed ? '✓' : '✗'}
                  </div>
                  <span className="text-xs text-muted" style={{ width: 24 }}>{key.slice(0, 2).toUpperCase()}</span>
                  <span style={{ color: passed ? 'var(--text)' : 'var(--muted)' }}>{label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Key Technical Levels Tab */}
      {tab === 'trade' && (
        <div>
          <div className="compliance-notice" style={{
            background: 'rgba(212,160,36,0.08)',
            border: '1px solid rgba(212,160,36,0.25)',
            borderRadius: 8,
            padding: '10px 16px',
            marginBottom: 12,
            fontSize: 11,
            color: 'var(--muted)',
            lineHeight: 1.5
          }}>
            <strong style={{ color: 'var(--amber)' }}>Illustrative only:</strong> These levels are auto-calculated
            from historical price data (support/resistance, ATR) and are NOT buy/sell recommendations.
            Do your own research before investing.
          </div>
          <div className="card mb-6">
            <div className="card-title">Illustrative Technical Levels — {ts.setup_type || 'N/A'}</div>
            <div className="trade-setup">
              <div className="ts-item">
                <div className="ts-label">Near Support</div>
                <div className="ts-value text-cyan">{formatNum(ts.entry)}</div>
              </div>
              <div className="ts-item">
                <div className="ts-label">ATR Risk Level</div>
                <div className="ts-value text-red">{formatNum(ts.stop_loss)}</div>
              </div>
              <div className="ts-item">
                <div className="ts-label">Resistance 1</div>
                <div className="ts-value text-green">{formatNum(ts.target1)}</div>
              </div>
              <div className="ts-item">
                <div className="ts-label">Resistance 2</div>
                <div className="ts-value text-green">{formatNum(ts.target2)}</div>
              </div>
            </div>

            <div className="grid-3" style={{ marginTop: 16 }}>
              <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                <div className="text-xs text-muted">Risk %</div>
                <div className="font-bold" style={{ color: ts.risk_pct <= 5 ? 'var(--green)' : 'var(--amber)' }}>
                  {ts.risk_pct?.toFixed(2)}%
                </div>
              </div>
              <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                <div className="text-xs text-muted">R:R Ratio</div>
                <div className="font-bold" style={{ color: ts.rr_ratio >= 2 ? 'var(--green)' : 'var(--amber)' }}>
                  1:{ts.rr_ratio?.toFixed(1)}
                </div>
              </div>
              <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                <div className="text-xs text-muted">Setup Type</div>
                <div className="font-bold text-cyan">{ts.setup_type || '—'}</div>
              </div>
            </div>
          </div>

          {/* Position Sizing Calculator */}
          <div className="card">
            <div className="card-title">Hypothetical Position Calculator (₹5,00,000 Capital / 2% Risk)</div>
            {(() => {
              const capital = 500000;
              const riskPct = 2;
              const riskAmount = capital * riskPct / 100;
              const riskPerShare = (ts.entry || 0) - (ts.stop_loss || 0);
              const qty = riskPerShare > 0 ? Math.floor(riskAmount / riskPerShare) : 0;
              const posValue = qty * (ts.entry || 0);

              return (
                <div className="grid-4">
                  <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                    <div className="text-xs text-muted">Quantity</div>
                    <div className="font-bold text-xl">{qty}</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                    <div className="text-xs text-muted">Position Value</div>
                    <div className="font-bold">{formatNum(posValue)}</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                    <div className="text-xs text-muted">Max Risk</div>
                    <div className="font-bold text-red">{formatNum(riskAmount)}</div>
                  </div>
                  <div style={{ textAlign: 'center', padding: 12, background: 'var(--bg4)', borderRadius: 8 }}>
                    <div className="text-xs text-muted">Risk/Share</div>
                    <div className="font-bold">{formatNum(riskPerShare)}</div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Institutional Tab */}
      {tab === 'institutional' && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title">Promoter Activity (SEBI Data)</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                ['Promoter Holding', `${promo.promoter_holding?.toFixed(2)}%`, 'var(--text)'],
                ['QoQ Change', formatPct(promo.promoter_chg_qoq), promo.promoter_chg_qoq >= 0 ? 'var(--green)' : 'var(--red)'],
                ['Pledge %', `${promo.pledge_pct?.toFixed(2)}%`, promo.pledge_pct > 10 ? 'var(--red)' : 'var(--green)'],
                ['Status', promo.promoter_buying ? 'BUYING' : promo.promoter_selling ? 'SELLING' : 'No change',
                 promo.promoter_buying ? 'var(--green)' : promo.promoter_selling ? 'var(--red)' : 'var(--muted)'],
              ].map(([label, val, color]) => (
                <div key={label} className="flex items-center justify-between" style={{ fontSize: 13 }}>
                  <span className="text-muted">{label}</span>
                  <span style={{ fontWeight: 600, color }}>{val}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">Open Interest & Bulk Deals</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span className="text-muted">OI Buildup</span>
                <span className={`signal-tag ${
                  stock.oi_data?.buildup_type === 'LongBuildup' || stock.oi_data?.buildup_type === 'ShortCovering' ? 'bullish' :
                  stock.oi_data?.buildup_type === 'ShortBuildup' || stock.oi_data?.buildup_type === 'LongUnwinding' ? 'bearish' : 'neutral'
                }`}>
                  {stock.oi_data?.buildup_type || 'N/A'}
                </span>
              </div>
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span className="text-muted">OI Change %</span>
                <span style={{ color: stock.oi_data?.oi_change_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {stock.oi_data?.oi_change_pct?.toFixed(2)}%
                </span>
              </div>
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span className="text-muted">Bulk Buy</span>
                <span style={{ color: stock.bulk_deal?.bulk_buy ? 'var(--green)' : 'var(--muted)' }}>
                  {stock.bulk_deal?.bulk_buy ? 'YES' : 'No'}
                </span>
              </div>
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span className="text-muted">Block Buy</span>
                <span style={{ color: stock.bulk_deal?.block_buy ? 'var(--green)' : 'var(--muted)' }}>
                  {stock.bulk_deal?.block_buy ? 'YES' : 'No'}
                </span>
              </div>
              <div className="flex items-center justify-between" style={{ fontSize: 13 }}>
                <span className="text-muted">Bulk Sell</span>
                <span style={{ color: stock.bulk_deal?.bulk_sell ? 'var(--red)' : 'var(--muted)' }}>
                  {stock.bulk_deal?.bulk_sell ? 'YES — CAUTION' : 'No'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Score Breakdown Tab */}
      {tab === 'breakdown' && (
        <div className="card">
          <div className="card-title">Score Breakdown — Total: {stock.score}/100</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(SCORE_LABELS).map(([key, meta]) => {
              const val = breakdown[key] || 0;
              const isNeg = val < 0;
              const maxAbs = Math.max(Math.abs(meta.max), 15);
              const barWidth = Math.abs(val) / maxAbs * 100;

              return (
                <div key={key} className="flex items-center gap-2" style={{ fontSize: 13 }}>
                  <span style={{ width: 24 }}>{meta.icon}</span>
                  <span className="text-muted" style={{ width: 140, flexShrink: 0 }}>{meta.label}</span>
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="score-bar" style={{ flex: 1 }}>
                      <div className="fill" style={{
                        width: `${Math.min(barWidth, 100)}%`,
                        background: isNeg ? 'var(--red)' : val > 0 ? 'var(--green)' : 'var(--muted)'
                      }} />
                    </div>
                    <span className="font-mono font-bold" style={{
                      width: 40, textAlign: 'right',
                      color: isNeg ? 'var(--red)' : val > 0 ? 'var(--green)' : 'var(--muted)'
                    }}>
                      {val > 0 ? '+' : ''}{val}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default StockDetail;

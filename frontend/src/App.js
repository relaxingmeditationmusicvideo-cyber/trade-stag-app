import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Scanner from './pages/Scanner';
import StockDetail from './pages/StockDetail';
import Sectors from './pages/Sectors';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Pricing from './pages/Pricing';
import Disclaimer from './pages/Disclaimer';
import Terms from './pages/Terms';
import Privacy from './pages/Privacy';
import PublicLayout from './components/PublicLayout';
import ProtectedRoute from './components/ProtectedRoute';
import DisclaimerModal from './components/DisclaimerModal';
import { AuthProvider, useAuth } from './AuthContext';

// Empty string = relative URL → browser uses current domain automatically.
// In dev: set REACT_APP_API_URL=http://localhost:8000 in .env
const API = process.env.REACT_APP_API_URL || '';

// ─── Sidebar groups — SEBI-neutral, StockMagnets-inspired labels ───
const SIDEBAR_GROUPS = [
  {
    label: 'Momentum & Technical',
    items: [
      { id: 'all',          label: 'All Stocks',           icon: '📊' },
      { id: 'aplus',        label: '52 Week Leaders',      icon: '⭐', badge: 'HOT' },
      { id: 'expert',       label: 'Multi-Factor Score',   icon: '🎯' },
      { id: 'trade',        label: 'Strong Grade Picks',   icon: '💡' },
      { id: 'breakouts',    label: 'Breakout Scanner',     icon: '⚡' },
      { id: 'volsurge',     label: 'Volume Breakout',      icon: '🔥' },
      { id: 'accumulation', label: 'Accumulation Zone',    icon: '🏦' },
    ],
  },
  {
    label: 'Price & Pattern',
    items: [
      { id: 'ema',          label: 'Golden Crossover',     icon: '📈', badge: 'NEW' },
      { id: 'vcp',          label: 'VCP Formation',        icon: '🔷' },
      { id: 'rs',           label: 'RS Momentum',          icon: '🚀' },
      { id: 'stage2',       label: 'Stage 2 Uptrend',      icon: '✅' },
      { id: 'price_action', label: 'Price Action',         icon: '📉' },
    ],
  },
  {
    label: 'Value & Quality',
    items: [
      { id: 'fundamentals',   label: 'Fundamental Score',    icon: '💎' },
      { id: 'value_screen',   label: 'Undervalued Growth',   icon: '💰' },
      { id: 'quality_screen', label: 'Quality & Blue Chips', icon: '🏆' },
    ],
  },
  {
    label: 'Market Overview',
    items: [
      { id: 'sectors',      label: 'Sector Strength',        icon: '🏭' },
    ],
  },
];

function Sidebar({ counts }) {
  const location = useLocation();
  const { user, logout } = useAuth();
  const path = location.pathname;
  const isHome = path === '/app' || path === '/app/dashboard' || path === '/app/';
  const currentScanner = path.startsWith('/app/scanner/') ? path.split('/')[3] : null;
  const onSectors = path === '/app/sectors';

  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        <Link to="/" className="sidebar-logo-mark">
          <span className="brand-antler">🦌</span>
          <span className="text-emerald">Trade</span><span className="text-gold">Stag</span>
        </Link>
        <div className="sidebar-logo-sub">NSE 500 · India</div>
        <div className="sidebar-tagline">Screener & Analysis Platform</div>
      </div>

      <div className="sidebar-section">
        <div className="sidebar-section-label">Overview</div>
        <Link to="/app" className={`sidebar-link ${isHome ? 'active' : ''}`}>
          <span className="si-icon">🏠</span>
          <span className="si-label">Dashboard</span>
        </Link>
      </div>

      {SIDEBAR_GROUPS.map(group => (
        <div className="sidebar-section" key={group.label}>
          <div className="sidebar-section-label">{group.label}</div>
          {group.items.map(item => {
            const isSectors = item.id === 'sectors';
            const target = isSectors ? '/app/sectors' : `/app/scanner/${item.id}`;
            const isActive = isSectors ? onSectors : (currentScanner === item.id);
            const count = counts?.[item.id];
            return (
              <Link key={item.id} to={target} className={`sidebar-link ${isActive ? 'active' : ''}`}>
                <span className="si-icon">{item.icon}</span>
                <span className="si-label">{item.label}</span>
                {count != null && <span className="si-count">{count}</span>}
                {item.badge && <span className={`si-badge ${item.badge.toLowerCase()}`}>{item.badge}</span>}
              </Link>
            );
          })}
        </div>
      ))}

      <div style={{ flex: 1 }} />
      <div className="sidebar-section sidebar-user">
        {user && (
          <>
            <div className="sidebar-user-name">{user.name || user.email}</div>
            <div className="sidebar-user-plan">{user.plan || 'Free'} plan</div>
            <button className="sidebar-logout" onClick={logout}>Log out</button>
          </>
        )}
        <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 8 }}>
          v7.2 — Educational use only
        </div>
      </div>
    </nav>
  );
}

// Safe number extractor — handles plain numbers AND {value, change, pct} shapes
export function num(x) {
  if (x == null) return null;
  if (typeof x === 'number') return isNaN(x) ? null : x;
  if (typeof x === 'string') { const n = parseFloat(x); return isNaN(n) ? null : n; }
  if (typeof x === 'object') {
    if (typeof x.value === 'number') return x.value;
    if (typeof x.val === 'number') return x.val;
    if (typeof x.pct === 'number') return x.pct;
  }
  return null;
}
export function fmt(x, digits = 2) {
  const n = num(x);
  return n == null ? null : n.toFixed(digits);
}

// Top stats bar
function TopStats({ pulse, total, lastScan }) {
  const fii = num(pulse?.fii_dii?.fii_net ?? pulse?.fii_dii?.fii);
  const dii = num(pulse?.fii_dii?.dii_net ?? pulse?.fii_dii?.dii);
  const pcr = num(pulse?.pcr?.nifty_pcr ?? pulse?.pcr?.pcr ?? pulse?.pcr);
  const vix = num(pulse?.india_vix ?? pulse?.vix);
  const breadth = num(pulse?.breadth?.pct ?? pulse?.breadth);
  return (
    <div className="topbar-stats">
      {lastScan && <span className="ts hl">Generated: <strong>{new Date(lastScan).toLocaleString('en-IN', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })}</strong></span>}
      <span className="ts">Universe: <strong>{total || '—'} stocks</strong></span>
      {fii != null && <span className={`ts ${fii >= 0 ? 'up' : 'dn'}`}>FII: <strong>{fii >= 0 ? '+' : ''}{fii.toFixed(0)} Cr</strong></span>}
      {dii != null && <span className={`ts ${dii >= 0 ? 'up' : 'dn'}`}>DII: <strong>{dii >= 0 ? '+' : ''}{dii.toFixed(0)} Cr</strong></span>}
      {pcr != null && <span className="ts">PCR: <strong className="text-cyan">{pcr.toFixed(2)}</strong></span>}
      {vix != null && <span className="ts">VIX: <strong className="text-amber">{vix.toFixed(2)}</strong></span>}
      {breadth != null && <span className="ts">Breadth: <strong>{breadth.toFixed(1)}%</strong></span>}
    </div>
  );
}

// Shared data hook
function useAllStocks(api) {
  const [data, setData] = useState({ stocks: [], counts: {}, sectors: [], market_pulse: {}, total: 0, last_scan: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    fetch(`${api}/api/all`)
      .then(r => r.json())
      .then(d => { setData(d || {}); setError(d?.error || null); setLoading(false); })
      .catch(e => { setError(String(e)); setLoading(false); });
  }, [api]);

  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}

// ─── Authenticated app shell ───
function AppShell() {
  const { data, loading, error, reload } = useAllStocks(API);
  return (
    <div className="app-layout">
      <DisclaimerModal />
      <div className="main-container">
        <Sidebar counts={data.counts} />
        <main className="content">
          <div className="topbar">
            <div className="topbar-title">
              <span className="topbar-breadcrumb">Trade Stag</span>
              <span className="topbar-sep">›</span>
              <span id="topbar-section-name">Live Scanner</span>
            </div>
            <TopStats pulse={data.market_pulse} total={data.total} lastScan={data.last_scan} />
            <button className="refresh-btn" onClick={reload} title="Reload data">↻</button>
          </div>
          <div className="content-area">
            {error && <div className="alert">⚠️ {error}</div>}
            <Routes>
              <Route path="/"                  element={<Dashboard data={data} loading={loading} api={API} />} />
              <Route path="/dashboard"         element={<Dashboard data={data} loading={loading} api={API} />} />
              <Route path="/scanner/:scanner"  element={<Scanner data={data} loading={loading} api={API} />} />
              <Route path="/stock/:symbol"     element={<StockDetail api={API} />} />
              <Route path="/sectors"           element={<Sectors api={API} sectors={data.sectors} />} />
              <Route path="*"                  element={<Navigate to="/app" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public routes with marketing layout */}
          <Route path="/"           element={<PublicLayout><Landing /></PublicLayout>} />
          <Route path="/login"      element={<PublicLayout><Login /></PublicLayout>} />
          <Route path="/signup"     element={<PublicLayout><Signup /></PublicLayout>} />
          <Route path="/pricing"    element={<PublicLayout><Pricing /></PublicLayout>} />
          <Route path="/disclaimer" element={<PublicLayout><Disclaimer /></PublicLayout>} />
          <Route path="/terms"      element={<PublicLayout><Terms /></PublicLayout>} />
          <Route path="/privacy"    element={<PublicLayout><Privacy /></PublicLayout>} />

          {/* Authenticated app — all /app/* routes are protected */}
          <Route path="/app/*" element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          } />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

// Helper functions
export function formatNum(n) {
  if (n == null || isNaN(n)) return '—';
  if (Math.abs(n) >= 10000000) return `₹${(n / 10000000).toFixed(2)}Cr`;
  if (Math.abs(n) >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  return `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function formatPrice(n) {
  if (n == null || isNaN(n) || n === 0) return '—';
  return `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPct(n) {
  if (n == null || isNaN(n)) return '—';
  const sign = n >= 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

export function gradeBg(g) {
  switch(g) {
    case 'A+': return '#059669';
    case 'A':  return '#10b981';
    case 'B+': return '#06b6d4';
    case 'B':  return '#f59e0b';
    case 'C':  return '#fb923c';
    case 'D':  return '#ef4444';
    default:   return '#4a5568';
  }
}

export function gradeClass(g) {
  if (g === 'A+') return 'A-plus';
  if (g === 'B+') return 'B-plus';
  return g || '';
}

export function getScoreColor(score) {
  if (score >= 80) return 'var(--green)';
  if (score >= 60) return 'var(--cyan)';
  if (score >= 40) return 'var(--amber)';
  return 'var(--red)';
}

export { API };
export default App;

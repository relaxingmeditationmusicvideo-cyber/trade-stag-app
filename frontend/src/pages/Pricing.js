import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';

// Trade Stag is positioned as an educational screening tool.

const FEATURES = [
  'Daily NSE 500 scan (auto-updated after market close)',
  'All 20+ screening tools including AVWAP Pre-Breakout Scanner',
  'Full stock data cards with technical indicators',
  'Pattern detection (VCP, Breakout, NR7, AVWAP...)',
  'Sector strength analytics',
  'Score breakdowns & multi-factor analysis',
  'Institutional accumulation detection',
  'Smart money & delivery analysis',
  'Stage 2 uptrend scanner',
  'Fundamental screening & quality scores',
];

const FAQ = [
  { q: 'Is Trade Stag giving investment advice?',
    a: 'No. Trade Stag is an information platform and screening tool. It processes publicly available end-of-day data and presents patterns, scores, and screener matches for educational and informational purposes. Nothing displayed constitutes investment advice or a recommendation to buy, sell, or hold any security. Trade Stag is not a SEBI-registered Investment Adviser or Research Analyst. Always consult a SEBI-registered professional before making investment decisions.' },
  { q: 'How do I get access?',
    a: 'Sign up for an account and your request will be sent to the admin for approval. Once approved, you will receive an email confirmation and get full access to all features.' },
  { q: 'How fresh is the data?',
    a: 'Trade Stag runs a full NSE 500 scan after every market close (around 6-7 PM IST). All screeners, scores, and pattern detections are based on the latest end-of-day data.' },
  { q: 'Do you cover derivatives, BSE stocks, or mid/small caps outside NSE 500?',
    a: 'Currently we cover the NSE 500 universe only - the most liquid and widely tracked segment. We may expand to Nifty Midcap 150 and BSE in the future.' },
];


export default function Pricing() {
  const { user } = useAuth();

  return (
    <div className="pricing-page">
      <section className="pricing-hero">
        <h1>Get Full Access to Trade Stag</h1>
        <p>Sign up and get approved by admin for complete access to all scanners and tools.</p>
      </section>

      <section className="pricing-tiers" style={{ justifyContent: 'center' }}>
        <div className="tier-card tier-featured" style={{ maxWidth: 480 }}>
          <div className="tier-ribbon">Full Access</div>
          <div className="tier-name">Premium</div>
          <div className="tier-price">
            <span className="tier-price-num">Admin Approval</span>
          </div>
          <p className="tier-tagline">Sign up and get approved for full access to all features</p>

          {user ? (
            user.approved || user.is_owner ? (
              <Link to="/app" className="btn btn-primary btn-wide">Go to App</Link>
            ) : (
              <div style={{
                padding: '12px 20px', borderRadius: 8,
                background: 'rgba(212,160,36,0.15)', color: 'var(--amber)',
                textAlign: 'center', fontWeight: 600,
              }}>
                Pending Admin Approval
              </div>
            )
          ) : (
            <Link to="/signup" className="btn btn-primary btn-wide">Sign Up for Access</Link>
          )}

          <ul className="tier-features">
            {FEATURES.map(f => <li key={f}>&#10003; {f}</li>)}
          </ul>
        </div>
      </section>

      <section className="pricing-faq">
        <h2>Frequently asked questions</h2>
        <div className="faq-grid">
          {FAQ.map((f, i) => (
            <div className="faq-item" key={i}>
              <div className="faq-q">{f.q}</div>
              <p className="faq-a">{f.a}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pricing-disclaimer-box">
        <strong>Regulatory note:</strong> Trade Stag is an information platform and
        screening tool for educational and informational purposes. Trade Stag is NOT a
        SEBI-registered Investment Adviser, Research Analyst, or Portfolio Manager.
        Nothing displayed constitutes investment advice, a recommendation, or a solicitation
        to buy or sell any security. Investment in securities market are subject to market
        risks. Read all related documents carefully before investing. See full{' '}
        <Link to="/disclaimer">disclaimer</Link>.
      </section>
    </div>
  );
}

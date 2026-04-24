import React from 'react';
import { Link } from 'react-router-dom';

const FEATURES = [
  { icon: '📊', title: '20+ Screeners',
    desc: 'Technical, momentum, delivery, and fundamental screens built on the full NSE 500 universe. Updated after every market close.' },
  { icon: '🎯', title: 'Multi-Factor Scoring',
    desc: 'Every stock is scored on 10+ dimensions — trend, momentum, breadth, relative strength, fundamentals, accumulation — with transparent breakdowns.' },
  { icon: '🔍', title: 'Pattern Detection',
    desc: 'Automated detection of VCP, breakouts, pocket pivots, inside days, NR7, flat bases, and volume dry-up across 500 stocks.' },
  { icon: '💎', title: 'Value & Quality',
    desc: 'Undervalued Growth (Graham, Magic Formula, Low P/B, Low P/E) and Quality & Blue Chips (Coffee Can, High OPM) computed daily.' },
  { icon: '📈', title: 'Market Pulse',
    desc: 'FII/DII flows, PCR, India VIX, advance/decline, sector strength, and grade distribution — all in one glance.' },
  { icon: '🏭', title: 'Sector Strength',
    desc: 'Rank sectors by momentum, relative strength, and accumulation to focus your research on the strongest areas of the market.' },
];

const HOW_IT_WORKS = [
  { n: '1', t: 'We Scan', d: 'Every market day after close, Trade Stag runs the full analysis pipeline on all 500 NSE 500 stocks.' },
  { n: '2', t: 'We Score', d: 'Each stock is graded and scored on technical, momentum, and fundamental dimensions.' },
  { n: '3', t: 'You Research', d: 'Browse screeners, explore patterns, dive into individual stock scorecards to inform your own research.' },
];

export default function Landing() {
  return (
    <div className="landing">
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-badge">🇮🇳 Built for the Indian Market</div>
          <h1 className="hero-title">
            Technical & Fundamental <span className="text-cyan">Screening</span>
            <br />for the <span className="text-orange">NSE 500</span>
          </h1>
          <p className="hero-sub">
            Trade Stag scans the entire NSE 500 universe every market day and surfaces
            patterns, momentum, and fundamentals in one dashboard — so you can spend
            your research time on the stocks that matter.
          </p>
          <div className="hero-ctas">
            <Link to="/signup" className="btn btn-primary btn-lg">Sign Up for Access →</Link>
            <Link to="/pricing" className="btn btn-ghost btn-lg">Learn More</Link>
          </div>
          <p className="hero-disclaimer-tag">
            * Educational & research tool only. Not investment advice. See{' '}
            <Link to="/disclaimer">disclaimer</Link>.
          </p>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>What you get</h2>
          <p>Automated analysis across technical, fundamental, and market-pulse dimensions.</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map(f => (
            <div className="feature-card" key={f.title}>
              <div className="feature-icon">{f.icon}</div>
              <div className="feature-title">{f.title}</div>
              <p className="feature-desc">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section section-alt">
        <div className="section-head">
          <h2>How it works</h2>
        </div>
        <div className="how-grid">
          {HOW_IT_WORKS.map(s => (
            <div className="how-card" key={s.n}>
              <div className="how-num">{s.n}</div>
              <div className="how-title">{s.t}</div>
              <p className="how-desc">{s.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section cta-section">
        <div className="cta-box">
          <h2>Start screening the NSE 500 today</h2>
          <p>Free tier includes daily scans and 3 screeners. No card required.</p>
          <Link to="/signup" className="btn btn-primary btn-lg">Create Free Account</Link>
        </div>
      </section>
    </div>
  );
}

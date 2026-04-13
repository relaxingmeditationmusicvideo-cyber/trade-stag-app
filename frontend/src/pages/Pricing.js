import React from 'react';
import { Link } from 'react-router-dom';

// NOTE: These are placeholder tiers. Fee collection requires:
//  (1) SEBI Research Analyst registration (INH number) if offering analysis, OR
//  (2) Positioning strictly as an educational/data tool with appropriate licensing, OR
//  (3) SEBI Investment Adviser registration (INA number) if giving specific advice.
// See SEBI_COMPLIANCE.md before enabling payments.

const TIERS = [
  {
    id: 'free',
    name: 'Free',
    price: '₹0',
    period: '/forever',
    tagline: 'Try the tool with basic access',
    features: [
      'Daily NSE 500 scan',
      'Access to 3 core screeners',
      'Market pulse overview',
      'End-of-day data',
      'Community disclaimer',
    ],
    limitations: [
      'No historical scans',
      'No stock-level deep dive',
      'No sector analytics',
    ],
    cta: 'Start Free',
    href: '/signup',
    featured: false,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '₹499',
    period: '/month',
    tagline: 'Full screener access for serious researchers',
    features: [
      'Everything in Free',
      'All 15+ screeners',
      'Full stock scorecards',
      'Pattern detection (VCP, Breakout, NR7…)',
      'Sector strength analytics',
      'Score breakdowns',
      'Export to CSV',
      'Email support',
    ],
    limitations: [],
    cta: 'Upgrade to Pro',
    href: '/signup?plan=pro',
    featured: true,
  },
  {
    id: 'premium',
    name: 'Premium',
    price: '₹1,499',
    period: '/month',
    tagline: 'For active researchers who want everything',
    features: [
      'Everything in Pro',
      'Historical scans (90-day archive)',
      'Custom watchlists (coming soon)',
      'Advanced filters & combinations',
      'API access (beta)',
      'Priority support',
      'Weekly market summary email',
    ],
    limitations: [],
    cta: 'Upgrade to Premium',
    href: '/signup?plan=premium',
    featured: false,
  },
];

const FAQ = [
  { q: 'Is Trade Stag giving investment advice?',
    a: 'No. Trade Stag is a technical screening and educational tool. It analyzes publicly available end-of-day data and presents patterns, scores, and screener matches. Nothing displayed constitutes investment advice or a recommendation to buy or sell any security. Always consult a SEBI-registered adviser before making investment decisions.' },
  { q: 'Can I cancel any time?',
    a: 'Yes. Subscriptions are month-to-month and you can cancel from your account settings. Your access continues until the end of the current billing period.' },
  { q: 'Do you offer refunds?',
    a: 'We offer a 7-day refund window on new Pro and Premium subscriptions. After 7 days, subscriptions are non-refundable but can be cancelled to stop future billing.' },
  { q: 'How fresh is the data?',
    a: 'Trade Stag runs a full NSE 500 scan after every market close (around 6–7 PM IST). All screeners, scores, and pattern detections are based on the latest end-of-day data.' },
  { q: 'Do you cover derivatives, BSE stocks, or mid/small caps outside NSE 500?',
    a: 'Currently we cover the NSE 500 universe only — the most liquid and widely tracked segment. We may expand to Nifty Midcap 150 and BSE in the future.' },
];

export default function Pricing() {
  return (
    <div className="pricing-page">
      <section className="pricing-hero">
        <h1>Simple, transparent pricing</h1>
        <p>Start free. Upgrade when you need more.</p>
        <div className="pricing-toggle-note">💡 All plans include the daily NSE 500 scan.</div>
      </section>

      <section className="pricing-tiers">
        {TIERS.map(t => (
          <div key={t.id} className={`tier-card ${t.featured ? 'tier-featured' : ''}`}>
            {t.featured && <div className="tier-ribbon">Most Popular</div>}
            <div className="tier-name">{t.name}</div>
            <div className="tier-price">
              <span className="tier-price-num">{t.price}</span>
              <span className="tier-price-period">{t.period}</span>
            </div>
            <p className="tier-tagline">{t.tagline}</p>
            <Link to={t.href} className={`btn ${t.featured ? 'btn-primary' : 'btn-ghost'} btn-wide`}>
              {t.cta}
            </Link>
            <ul className="tier-features">
              {t.features.map(f => <li key={f}>✓ {f}</li>)}
              {t.limitations.map(f => <li key={f} className="tier-limit">— {f}</li>)}
            </ul>
          </div>
        ))}
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
        <strong>Regulatory note:</strong> Trade Stag is positioned as a technical
        screening & educational tool. It is not a SEBI-registered Research Analyst
        or Investment Adviser service. Nothing displayed constitutes investment
        advice. See full <Link to="/disclaimer">disclaimer</Link>.
      </section>
    </div>
  );
}

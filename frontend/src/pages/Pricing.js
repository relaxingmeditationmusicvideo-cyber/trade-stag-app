import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

const API = process.env.REACT_APP_API_URL || '';

// Trade Stag is positioned as an educational screening tool.
// Fee is for software access / data visualization — NOT for investment advice.

const TIERS = [
  {
    id: 'free',
    name: 'Free',
    price: '₹0',
    period: '/10 days',
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
    cta: 'Start Free Trial',
    featured: false,
    amount: 0,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '₹499',
    period: '/month',
    tagline: 'Full screening tools for active researchers',
    features: [
      'Everything in Free',
      'All 20+ screening tools',
      'Full stock data cards',
      'Pattern detection (VCP, Breakout, NR7...)',
      'Sector strength analytics',
      'Score breakdowns',
      'Export to CSV',
      'Email support',
    ],
    limitations: [],
    cta: 'Upgrade to Pro',
    featured: true,
    amount: 499,
  },
  {
    id: 'premium',
    name: 'Premium',
    price: '₹1,499',
    period: '/month',
    tagline: 'All tools and data for power users',
    features: [
      'Everything in Pro',
      'Historical scans (90-day archive)',
      'Custom watchlists (coming soon)',
      'Advanced filters & combinations',
      'API access (beta)',
      'Priority support',
      'Weekly market data digest',
    ],
    limitations: [],
    cta: 'Upgrade to Premium',
    featured: false,
    amount: 1499,
  },
];

const FAQ = [
  { q: 'Is Trade Stag giving investment advice?',
    a: 'No. Trade Stag is an information platform and screening tool. It processes publicly available end-of-day data and presents patterns, scores, and screener matches for educational and informational purposes. Nothing displayed constitutes investment advice or a recommendation to buy, sell, or hold any security. Trade Stag is not a SEBI-registered Investment Adviser or Research Analyst. Always consult a SEBI-registered professional before making investment decisions.' },
  { q: 'Can I cancel any time?',
    a: 'Yes. Subscriptions are month-to-month and you can cancel from your account settings. Your access continues until the end of the current billing period.' },
  { q: 'Do you offer refunds?',
    a: 'We offer a 7-day refund window on new Pro and Premium subscriptions. After 7 days, subscriptions are non-refundable but can be cancelled to stop future billing.' },
  { q: 'How fresh is the data?',
    a: 'Trade Stag runs a full NSE 500 scan after every market close (around 6-7 PM IST). All screeners, scores, and pattern detections are based on the latest end-of-day data.' },
  { q: 'Do you cover derivatives, BSE stocks, or mid/small caps outside NSE 500?',
    a: 'Currently we cover the NSE 500 universe only - the most liquid and widely tracked segment. We may expand to Nifty Midcap 150 and BSE in the future.' },
];


function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) { resolve(true); return; }
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}


export default function Pricing() {
  const { user, token, updateUser } = useAuth();
  const navigate = useNavigate();
  const [processing, setProcessing] = useState(null); // 'pro' or 'premium'
  const [error, setError] = useState(null);

  const handleUpgrade = async (plan) => {
    setError(null);

    // Not logged in — redirect to signup
    if (!user || !token) {
      navigate(`/signup?plan=${plan}`);
      return;
    }

    // Already on this plan or higher
    if (user.is_owner) {
      setError('You already have full access as the owner!');
      return;
    }
    if (user.effective_plan === plan || (plan === 'pro' && user.effective_plan === 'premium')) {
      setError(`You are already on the ${user.effective_plan} plan.`);
      return;
    }

    setProcessing(plan);

    try {
      // 1. Create order on backend
      const orderRes = await fetch(`${API}/api/auth/create-order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ plan }),
      });
      const orderData = await orderRes.json();

      if (!orderRes.ok) {
        throw new Error(orderData.detail || 'Failed to create order');
      }

      // Owner bypass
      if (orderData.status === 'owner_bypass') {
        updateUser(orderData.user);
        navigate('/app');
        return;
      }

      // 2. Load Razorpay
      const loaded = await loadRazorpayScript();
      if (!loaded) {
        throw new Error('Failed to load payment gateway. Please check your internet connection.');
      }

      // 3. Open Razorpay checkout
      const options = {
        key: orderData.key,
        amount: orderData.amount,
        currency: orderData.currency,
        name: 'Trade Stag',
        description: `${plan === 'pro' ? 'Pro' : 'Premium'} Plan - Monthly`,
        order_id: orderData.order_id,
        prefill: {
          email: orderData.user_email,
          name: orderData.user_name,
        },
        theme: {
          color: '#059669',
        },
        handler: async function (response) {
          // 4. Verify payment on backend
          try {
            const verifyRes = await fetch(`${API}/api/auth/verify-payment`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
              },
              body: JSON.stringify({
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });
            const verifyData = await verifyRes.json();

            if (verifyRes.ok && verifyData.status === 'success') {
              updateUser(verifyData.user);
              navigate('/app');
            } else {
              setError(verifyData.detail || 'Payment verification failed');
            }
          } catch (e) {
            setError('Payment verification error. Please contact support.');
          }
          setProcessing(null);
        },
        modal: {
          ondismiss: function () {
            setProcessing(null);
          },
        },
      };

      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (response) {
        setError(`Payment failed: ${response.error.description}`);
        setProcessing(null);
      });
      rzp.open();

    } catch (e) {
      setError(e.message);
      setProcessing(null);
    }
  };

  // Determine CTA for each tier based on user's current plan
  const getCtaLabel = (tier) => {
    if (!user) return tier.id === 'free' ? 'Start Free Trial' : tier.cta;
    if (user.is_owner) return 'Full Access';
    if (tier.id === 'free') return user.effective_plan === 'free' ? 'Current Plan' : 'Current Plan';
    if (user.effective_plan === tier.id) return 'Current Plan';
    if (tier.id === 'pro' && user.effective_plan === 'premium') return 'Downgrade';
    return tier.cta;
  };

  const isCurrentPlan = (tierId) => {
    if (!user) return false;
    if (user.is_owner) return tierId === 'premium';
    return user.effective_plan === tierId;
  };

  return (
    <div className="pricing-page">
      <section className="pricing-hero">
        <h1>Simple, transparent pricing</h1>
        <p>Start with a 10-day free trial. Upgrade when you need more.</p>
        <div className="pricing-toggle-note">All plans include the daily NSE 500 scan.</div>
      </section>

      {error && <div className="pricing-error">{error}</div>}

      <section className="pricing-tiers">
        {TIERS.map(t => (
          <div key={t.id} className={`tier-card ${t.featured ? 'tier-featured' : ''} ${isCurrentPlan(t.id) ? 'tier-current' : ''}`}>
            {t.featured && <div className="tier-ribbon">Most Popular</div>}
            {isCurrentPlan(t.id) && <div className="tier-ribbon tier-ribbon-current">Current Plan</div>}
            <div className="tier-name">{t.name}</div>
            <div className="tier-price">
              <span className="tier-price-num">{t.price}</span>
              <span className="tier-price-period">{t.period}</span>
            </div>
            <p className="tier-tagline">{t.tagline}</p>
            {t.id === 'free' ? (
              <Link to={user ? '/app' : '/signup'} className="btn btn-ghost btn-wide">
                {user ? 'Go to App' : 'Start Free Trial'}
              </Link>
            ) : (
              <button
                className={`btn ${t.featured ? 'btn-primary' : 'btn-ghost'} btn-wide`}
                onClick={() => handleUpgrade(t.id)}
                disabled={processing === t.id || isCurrentPlan(t.id)}
              >
                {processing === t.id ? 'Processing...' : getCtaLabel(t)}
              </button>
            )}
            <ul className="tier-features">
              {t.features.map(f => <li key={f}>&#10003; {f}</li>)}
              {t.limitations.map(f => <li key={f} className="tier-limit">- {f}</li>)}
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

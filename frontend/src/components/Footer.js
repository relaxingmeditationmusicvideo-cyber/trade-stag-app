import React from 'react';
import { Link } from 'react-router-dom';
import Logo from './Logo';

export default function Footer() {
  return (
    <footer className="site-footer">
      {/* ── Top row: brand + link columns ── */}
      <div className="footer-top">
        <div className="footer-brand-col">
          <Link to="/" className="footer-brand-link">
            <Logo size={22} variant="full" />
          </Link>
          <p className="footer-tagline">
            Smart screening tool for the Indian equity market.
          </p>
        </div>

        <div className="footer-links-col">
          <h4 className="footer-heading">Product</h4>
          <ul className="footer-list">
            <li><Link to="/pricing">Pricing</Link></li>
            <li><Link to="/signup">Sign Up</Link></li>
            <li><Link to="/login">Log In</Link></li>
          </ul>
        </div>

        <div className="footer-links-col">
          <h4 className="footer-heading">Legal</h4>
          <ul className="footer-list">
            <li><Link to="/disclaimer">Disclaimer</Link></li>
            <li><Link to="/terms">Terms of Service</Link></li>
            <li><Link to="/privacy">Privacy Policy</Link></li>
          </ul>
        </div>

        <div className="footer-links-col">
          <h4 className="footer-heading">Support</h4>
          <ul className="footer-list">
            <li><a href="mailto:support@tradestag.com">Contact</a></li>
          </ul>
        </div>
      </div>

      {/* ── Disclaimer banner ── */}
      <div className="footer-disclaimer">
        Investment in securities market are subject to market risks. Read all the
        related documents carefully before investing. Trade Stag is not a
        SEBI-registered Investment Adviser or Research Analyst. All content is for
        informational and educational purposes only and should not be construed as
        investment advice. Past performance is not indicative of future results.
      </div>

      {/* ── Bottom bar ── */}
      <div className="footer-bottom">
        <span>&copy; {new Date().getFullYear()} Trade Stag. All rights reserved.</span>
        <span className="footer-bottom-links">
          <Link to="/disclaimer">Disclaimer</Link>
          <span className="footer-dot">&middot;</span>
          <Link to="/terms">Terms</Link>
          <span className="footer-dot">&middot;</span>
          <Link to="/privacy">Privacy</Link>
        </span>
      </div>
    </footer>
  );
}

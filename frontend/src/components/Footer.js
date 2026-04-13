import React from 'react';
import { Link } from 'react-router-dom';

// NOTE: This footer displays a persistent SEBI disclaimer on every page.
// DO NOT REMOVE THIS COMPONENT. See SEBI_COMPLIANCE.md.
// Replace SEBI_RA_NUMBER below with your actual registration once issued.
const SEBI_RA_NUMBER = 'REGISTRATION PENDING'; // e.g., 'INH000XXXXXX'

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-grid">
        <div className="footer-col">
          <div className="footer-brand">
            <span className="text-amber">Trade</span> <span className="text-green">Stag</span>
          </div>
          <p className="footer-tag">
            Technical & fundamental screening tool for the Indian equity market.
            NSE 500 universe. EOD data.
          </p>
        </div>
        <div className="footer-col">
          <div className="footer-col-title">Product</div>
          <Link to="/pricing">Pricing</Link>
          <Link to="/login">Log in</Link>
          <Link to="/signup">Sign up</Link>
        </div>
        <div className="footer-col">
          <div className="footer-col-title">Legal</div>
          <Link to="/disclaimer">Disclaimer</Link>
          <Link to="/terms">Terms of Service</Link>
          <Link to="/privacy">Privacy Policy</Link>
        </div>
        <div className="footer-col">
          <div className="footer-col-title">SEBI</div>
          <div className="footer-sebi">SEBI RA No: <strong>{SEBI_RA_NUMBER}</strong></div>
          <div className="footer-sebi-note">
            Verify any RA/IA registration on the official SEBI website at sebi.gov.in
          </div>
        </div>
      </div>

      <div className="footer-disclaimer">
        <strong>IMPORTANT DISCLAIMER:</strong> Trade Stag is a technical screening and
        educational tool. Nothing displayed on this platform constitutes investment
        advice, a recommendation to buy or sell any security, or a research report
        under SEBI (Research Analysts) Regulations, 2014. All analysis is automated,
        based on publicly available end-of-day data, and is provided "as is" without
        any warranty of accuracy. Past performance does not indicate future results.
        Investments in securities are subject to market risks. Read all scheme-related
        documents carefully. Consult a SEBI-registered investment adviser before making
        any investment decision. Trade Stag and its operators accept no liability for
        any losses arising from use of this tool.
      </div>

      <div className="footer-copyright">
        © {new Date().getFullYear()} Trade Stag. All rights reserved.
      </div>
    </footer>
  );
}

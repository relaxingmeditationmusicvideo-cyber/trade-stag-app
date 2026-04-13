import React, { useState, useEffect } from 'react';

// NOTE: This is a mandatory first-visit disclaimer. The user must acknowledge
// before accessing any scanner data. Acknowledgement is stored in localStorage
// so it only appears once per browser. DO NOT REMOVE without legal advice.
const ACK_KEY = 'tradestag_disclaimer_ack_v1';

export default function DisclaimerModal() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(ACK_KEY)) setShow(true);
  }, []);

  const accept = () => {
    localStorage.setItem(ACK_KEY, String(Date.now()));
    setShow(false);
  };

  if (!show) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal-card disclaimer-modal">
        <h2>Important Notice — Please Read</h2>
        <div className="disclaimer-body">
          <p>
            <strong>Trade Stag is a technical screening and educational tool.</strong> It
            analyzes publicly available end-of-day data from the NSE 500 universe using
            automated technical and fundamental indicators.
          </p>
          <p>
            Nothing shown on this platform — including scores, grades, scanner matches,
            pattern detections, or illustrative technical ranges — constitutes:
          </p>
          <ul>
            <li>Investment advice</li>
            <li>A recommendation to buy or sell any security</li>
            <li>A research report under SEBI (Research Analysts) Regulations, 2014</li>
            <li>A promise or projection of future returns</li>
          </ul>
          <p>
            <strong>Investments in securities are subject to market risks.</strong> Past
            performance does not indicate future results. Consult a SEBI-registered
            investment adviser before making any investment decision.
          </p>
          <p className="disclaimer-small">
            By clicking "I Understand", you acknowledge that you have read and agreed
            to the above and to our full{' '}
            <a href="/disclaimer" target="_blank" rel="noopener">Disclaimer</a> and{' '}
            <a href="/terms" target="_blank" rel="noopener">Terms of Service</a>.
          </p>
        </div>
        <div className="modal-actions">
          <button className="btn btn-primary btn-wide" onClick={accept}>
            I Understand — Continue
          </button>
        </div>
      </div>
    </div>
  );
}

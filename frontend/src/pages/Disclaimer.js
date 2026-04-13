import React from 'react';

export default function Disclaimer() {
  return (
    <div className="legal-page">
      <h1>Disclaimer</h1>
      <p className="legal-updated">Last updated: {new Date().toLocaleDateString('en-IN', { year:'numeric', month:'long', day:'numeric' })}</p>

      <section>
        <h2>Nature of the service</h2>
        <p>
          Trade Stag is an automated technical and fundamental screening platform for
          the Indian equity market. It analyzes publicly available end-of-day data
          from the NSE 500 universe and presents screener results, scores, pattern
          detections, and illustrative technical indicators.
        </p>
        <p>
          Trade Stag is provided as an educational and research tool only. It is
          intended to help users narrow down a universe of stocks for their own
          further research.
        </p>
      </section>

      <section>
        <h2>Not investment advice</h2>
        <p>
          Nothing displayed on Trade Stag — including but not limited to scores,
          grades, screener matches, pattern detections, illustrative technical ranges,
          fundamental screens, or sector analytics — constitutes:
        </p>
        <ul>
          <li>Investment advice;</li>
          <li>A recommendation, solicitation, or offer to buy or sell any security;</li>
          <li>A research report under SEBI (Research Analysts) Regulations, 2014;</li>
          <li>A promise, projection, or guarantee of future returns;</li>
          <li>Advice regarding any specific investor's circumstances or suitability.</li>
        </ul>
      </section>

      <section>
        <h2>SEBI registration status</h2>
        <p>
          Trade Stag and its operators are positioned as providers of a technical
          screening and data-visualization tool. Users should verify the current
          SEBI registration status of Trade Stag (if any) on the official SEBI website
          at <a href="https://www.sebi.gov.in" target="_blank" rel="noopener">sebi.gov.in</a>.
        </p>
        <p>
          If you require personalized investment advice, please consult a SEBI-registered
          Investment Adviser (IA) or Research Analyst (RA).
        </p>
      </section>

      <section>
        <h2>Market risks</h2>
        <p>
          Investments in securities markets are subject to market risks. Read all
          scheme-related documents carefully before investing. Past performance of
          any security, screener, or strategy is not indicative of future results.
          The value of investments can fall as well as rise, and you may not recover
          the amount originally invested.
        </p>
      </section>

      <section>
        <h2>Accuracy of data</h2>
        <p>
          While Trade Stag strives to use accurate and up-to-date data, we make no
          warranty regarding the accuracy, completeness, timeliness, or reliability
          of any information presented. Data may be delayed, incomplete, or subject
          to errors in collection or processing. Users should independently verify
          any information before relying on it.
        </p>
      </section>

      <section>
        <h2>Limitation of liability</h2>
        <p>
          To the maximum extent permitted by applicable law, Trade Stag, its operators,
          employees, and affiliates accept no liability for any direct, indirect,
          incidental, consequential, or special damages arising out of or in connection
          with the use of, or inability to use, the platform — including but not limited
          to trading losses, missed opportunities, or reliance on any information
          displayed.
        </p>
      </section>

      <section>
        <h2>Your responsibility</h2>
        <p>
          You are solely responsible for your investment decisions. You should conduct
          your own due diligence and, where appropriate, seek advice from a qualified
          and SEBI-registered professional before acting on any information obtained
          through Trade Stag.
        </p>
      </section>

      <section>
        <h2>Contact</h2>
        <p>
          Questions about this disclaimer can be sent to: <em>support@tradestag.in</em>
          {' '}(replace with your actual support email before launch).
        </p>
      </section>
    </div>
  );
}

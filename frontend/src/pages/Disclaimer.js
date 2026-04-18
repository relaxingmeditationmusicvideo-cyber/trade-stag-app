import React from 'react';

export default function Disclaimer() {
  return (
    <div className="legal-page">
      <h1>Disclaimer</h1>
      <p className="legal-updated">Last updated: April 2026</p>

      <div className="legal-highlight" style={{
        background: 'rgba(212,160,36,0.08)',
        border: '1px solid rgba(212,160,36,0.2)',
        borderRadius: 8,
        padding: '16px 20px',
        marginBottom: 24,
        fontSize: 13,
        lineHeight: 1.7,
        color: 'var(--muted)'
      }}>
        <strong style={{ color: 'var(--amber)' }}>Important:</strong> Investment in securities market
        are subject to market risks. Read all the related documents carefully before investing.
        The information provided on Trade Stag is for informational and educational purposes only.
        It should not be construed as financial, investment, or trading advice.
      </div>

      <section>
        <h2>1. Not financial advice</h2>
        <p>
          Trade Stag is an information platform that provides market data, analytics, screeners,
          and tools for tracking Indian equities. The content on this platform, including but not
          limited to stock data, scores, grades, screener matches, pattern detections, illustrative
          technical levels, fundamental screens, sector analytics, or any other features:
        </p>
        <ul>
          <li>Is NOT financial, investment, legal, or tax advice;</li>
          <li>Is NOT a sole basis for any investment decision;</li>
          <li>Is NOT a recommendation to buy, sell, or hold any security;</li>
          <li>Is NOT personalized or tailored to your specific financial situation.</li>
        </ul>
      </section>

      <section>
        <h2>2. No guarantees</h2>
        <p>We make no representations or warranties regarding:</p>
        <ul>
          <li><strong>Accuracy</strong> — the accuracy, completeness, or timeliness of any information;</li>
          <li><strong>Future performance</strong> — future performance of any security or market;</li>
          <li><strong>Suitability</strong> — the suitability of any investment for your circumstances;</li>
          <li><strong>Reliability</strong> — the reliability or availability of our services.</li>
        </ul>
      </section>

      <section>
        <h2>3. Investment risks</h2>
        <p>
          Investing in securities involves substantial risk. You should be aware of the following:
        </p>
        <ul>
          <li><strong>Market risk</strong> — The value of investments can go down as well as up;</li>
          <li><strong>Volatility risk</strong> — Markets can experience significant short-term fluctuations;</li>
          <li><strong>Liquidity risk</strong> — You may not be able to sell investments at desired prices;</li>
          <li><strong>Capital loss</strong> — You may lose some or all of your invested capital.</li>
        </ul>
        <p>
          Past performance is not indicative of future results. Historical data shown on our
          platform does not guarantee similar future performance.
        </p>
      </section>

      <section>
        <h2>4. Data sources and accuracy</h2>
        <p>
          Market data, financial information, and other content displayed on Trade Stag is sourced
          from publicly available sources including NSE bhavcopy archives and other third-party
          providers. While we strive to provide accurate information:
        </p>
        <ul>
          <li>Data may be delayed, incomplete, or contain errors;</li>
          <li>We cannot guarantee the accuracy or timeliness of all information;</li>
          <li>Third-party data is provided "as is" without verification;</li>
          <li>Corporate actions, dividends, and events data may have discrepancies.</li>
        </ul>
        <p>
          Always verify critical information with official sources such as stock exchanges (NSE, BSE),
          company filings, or your broker before making investment decisions.
        </p>
      </section>

      <section>
        <h2>5. Technical analysis and screeners</h2>
        <p>Our technical analysis tools, stock screeners, scores, grades, and algorithms:</p>
        <ul>
          <li>Are based on historical data and mathematical formulas;</li>
          <li>May not account for all market factors or conditions;</li>
          <li>Should not be relied upon as the sole decision-making tool;</li>
          <li>May produce different results based on data timing and availability.</li>
        </ul>
        <p>
          Any illustrative technical levels (support, resistance, ATR-based ranges) shown on the
          platform are auto-calculated from historical price data and do not constitute buy, sell,
          or hold recommendations.
        </p>
      </section>

      <section>
        <h2>6. SEBI compliance</h2>
        <p>Trade Stag is an information and screening platform and is NOT:</p>
        <ul>
          <li>NOT a SEBI-registered Investment Adviser (IA);</li>
          <li>NOT a SEBI-registered Research Analyst (RA);</li>
          <li>NOT a SEBI-registered Portfolio Manager;</li>
          <li>NOT a Stock Broker or Trading Platform.</li>
        </ul>
        <p>
          We do not provide personalized investment recommendations or manage client portfolios.
          If you require personalized investment advice, please consult a SEBI-registered
          Investment Adviser or Research Analyst. You can verify registration status on the
          official SEBI website at{' '}
          <a href="https://www.sebi.gov.in" target="_blank" rel="noopener noreferrer">sebi.gov.in</a>.
        </p>
      </section>

      <section>
        <h2>7. Consult professionals</h2>
        <p>Before making any investment decision, we strongly recommend that you:</p>
        <ul>
          <li>Consult a qualified and SEBI-registered financial adviser;</li>
          <li>Conduct your own thorough research and due diligence;</li>
          <li>Consider your financial goals, risk tolerance, and investment horizon;</li>
          <li>Understand the specific risks of each investment;</li>
          <li>Review official company filings and disclosures.</li>
        </ul>
      </section>

      <section>
        <h2>8. Limitation of liability</h2>
        <p>
          To the fullest extent permitted by applicable law, Trade Stag, its operators, directors,
          employees, partners, and affiliates shall not be liable for any direct, indirect,
          incidental, consequential, or punitive damages arising from:
        </p>
        <ul>
          <li>Your use of, or inability to use, our services;</li>
          <li>Any investment decisions made based on information from our platform;</li>
          <li>Errors, inaccuracies, or omissions in the content;</li>
          <li>Technical failures, delays, or interruptions;</li>
          <li>Unauthorized access to your account or data.</li>
        </ul>
      </section>

      <section>
        <h2>9. External links</h2>
        <p>
          Our platform may contain links to external websites. We are not responsible for the
          content, accuracy, or practices of these third-party sites.
        </p>
      </section>

      <section>
        <h2>10. Changes to disclaimer</h2>
        <p>
          We reserve the right to modify this disclaimer at any time. Changes will be effective
          immediately upon posting to this page.
        </p>
      </section>

      <section>
        <h2>11. Contact</h2>
        <p>
          If you have questions about this disclaimer, please contact us
          at: <a href="mailto:support@tradestag.com">support@tradestag.com</a>
        </p>
        <p style={{ marginTop: 16, fontStyle: 'italic', color: 'var(--muted)', fontSize: 13 }}>
          By using Trade Stag, you acknowledge that you have read, understood, and agree to this
          disclaimer. You accept full responsibility for your investment decisions.
        </p>
      </section>
    </div>
  );
}

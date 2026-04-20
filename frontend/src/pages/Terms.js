import React from 'react';

export default function Terms() {
  return (
    <div className="legal-page">
      <h1>Terms of Service</h1>
      <p className="legal-updated">Last updated: {new Date().toLocaleDateString('en-IN', { year:'numeric', month:'long', day:'numeric' })}</p>

      <section>
        <h2>1. Acceptance</h2>
        <p>By creating an account or using Trade Stag, you agree to these Terms of Service
        and to our <a href="/disclaimer">Disclaimer</a> and <a href="/privacy">Privacy Policy</a>.
        If you do not agree, do not use the service.</p>
      </section>

      <section>
        <h2>2. Eligibility</h2>
        <p>You must be at least 18 years old and legally capable of entering into a
        contract under Indian law to use Trade Stag.</p>
      </section>

      <section>
        <h2>3. Account security</h2>
        <p>You are responsible for maintaining the confidentiality of your account
        credentials and for all activity under your account. Notify us immediately
        of any unauthorized access.</p>
      </section>

      <section>
        <h2>4. Subscription & billing</h2>
        <p>Paid plans (Pro, Premium) are billed in advance on a monthly basis. You
        may cancel any time; cancellation takes effect at the end of the current
        billing period and there is no pro-rated refund thereafter. New subscribers
        may request a full refund within 7 days of the initial purchase.</p>
      </section>

      <section>
        <h2>5. Acceptable use</h2>
        <p>You agree not to: (a) scrape or redistribute Trade Stag data; (b) resell
        access; (c) use the service to provide unregistered investment advice to
        third parties; (d) attempt to circumvent authentication or rate limits;
        (e) use the service for any unlawful purpose.</p>
      </section>

      <section>
        <h2>6. Not investment advice</h2>
        <p>Trade Stag is a technical screening and educational tool. It does not
        provide investment, legal, tax, or other professional advice. See our
        full <a href="/disclaimer">Disclaimer</a>.</p>
      </section>

      <section>
        <h2>7. Termination</h2>
        <p>We may suspend or terminate your access at any time for violation of
        these terms, for non-payment, or at our discretion with reasonable notice.</p>
      </section>

      <section>
        <h2>8. Governing law</h2>
        <p>These terms are governed by the laws of India. Any disputes shall be
        subject to the exclusive jurisdiction of the courts in New Delhi, India.</p>
      </section>

      <section>
        <h2>9. Changes</h2>
        <p>We may update these terms from time to time. Material changes will be
        notified via email or prominent notice on the platform.</p>
      </section>

      <section>
        <h2>10. Grievance Redressal</h2>
        <p>If you have any grievances or complaints regarding the service, you may
        contact our Grievance Officer at <a href="mailto:support@tradestag.com">support@tradestag.com</a>.
        We will acknowledge your complaint within 48 hours and endeavour to resolve
        it within 30 days of receipt.</p>
      </section>
    </div>
  );
}

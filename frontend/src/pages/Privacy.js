import React from 'react';

export default function Privacy() {
  return (
    <div className="legal-page">
      <h1>Privacy Policy</h1>
      <p className="legal-updated">Last updated: {new Date().toLocaleDateString('en-IN', { year:'numeric', month:'long', day:'numeric' })}</p>

      <section>
        <h2>1. What we collect</h2>
        <p>When you sign up for Trade Stag we collect: your name, email address,
        and a hashed password. We do not store your plain-text password.</p>
        <p>We also log basic usage data: pages visited, timestamps, and IP address,
        for analytics and abuse prevention.</p>
      </section>

      <section>
        <h2>2. How we use it</h2>
        <p>We use your data to: provide and improve the service, authenticate you,
        send you important service notices, respond to support requests, and comply
        with legal obligations. We do not sell your personal data.</p>
      </section>

      <section>
        <h2>3. Data sharing</h2>
        <p>We share data only with: (a) payment processors to process subscriptions;
        (b) hosting and email providers needed to run the service; (c) authorities
        when required by law.</p>
      </section>

      <section>
        <h2>4. Data retention</h2>
        <p>We retain account data while your account is active and for a reasonable
        period thereafter to comply with legal obligations and resolve disputes.</p>
      </section>

      <section>
        <h2>5. Your rights</h2>
        <p>You may access, correct, or delete your personal data by emailing
        <em> support@tradestag.in</em>. You may close your account at any time.</p>
      </section>

      <section>
        <h2>6. Cookies</h2>
        <p>We use minimal cookies / localStorage items strictly required for
        authentication and for remembering your disclaimer acknowledgement. We do
        not use tracking or advertising cookies.</p>
      </section>

      <section>
        <h2>7. Security</h2>
        <p>We store passwords using bcrypt hashing and use HTTPS for all data in
        transit. No system is perfectly secure, and we cannot guarantee absolute
        security of data.</p>
      </section>

      <section>
        <h2>8. Contact</h2>
        <p>Privacy questions: <em>support@tradestag.in</em> (update before launch).</p>
      </section>
    </div>
  );
}

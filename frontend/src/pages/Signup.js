import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export default function Signup() {
  const { signup, loading, error } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [ack, setAck] = useState(false);
  const [localError, setLocalError] = useState(null);
  const navigate = useNavigate();

  const onSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);
    if (!email || !password) { setLocalError('Email and password required'); return; }
    if (password.length < 8) { setLocalError('Password must be at least 8 characters'); return; }
    if (password !== confirm) { setLocalError('Passwords do not match'); return; }
    if (!ack) { setLocalError('You must acknowledge the disclaimer to continue'); return; }
    const res = await signup({ email, password, name });
    if (res.ok) navigate('/app', { replace: true });
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>Create account</h1>
          <p>Start screening the NSE 500 in minutes</p>
        </div>
        <form onSubmit={onSubmit} className="auth-form">
          <label>
            Name
            <input type="text" value={name} onChange={e => setName(e.target.value)}
              autoComplete="name" placeholder="Your name" />
          </label>
          <label>
            Email
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              autoComplete="email" required placeholder="you@example.com" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              autoComplete="new-password" required placeholder="min 8 characters" />
          </label>
          <label>
            Confirm password
            <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)}
              autoComplete="new-password" required placeholder="repeat password" />
          </label>

          <label className="auth-ack">
            <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
            <span>
              I understand that Trade Stag is a technical screening & educational tool
              and does not provide investment advice or recommendations. I have read
              and agree to the <Link to="/disclaimer" target="_blank">Disclaimer</Link>,{' '}
              <Link to="/terms" target="_blank">Terms</Link> and{' '}
              <Link to="/privacy" target="_blank">Privacy Policy</Link>.
            </span>
          </label>

          {(error || localError) && (
            <div className="auth-error">⚠️ {localError || error}</div>
          )}

          <button type="submit" className="btn btn-primary btn-wide" disabled={loading}>
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <div className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export default function Login() {
  const { login, loading, error } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || '/app';

  const onSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);
    if (!email || !password) { setLocalError('Email and password required'); return; }
    const res = await login({ email, password });
    if (res.ok) navigate(from, { replace: true });
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>Welcome back</h1>
          <p>Log in to access your screeners</p>
        </div>
        <form onSubmit={onSubmit} className="auth-form">
          <label>
            Email
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              autoComplete="email" required placeholder="you@example.com" />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              autoComplete="current-password" required placeholder="••••••••" />
          </label>
          {(error || localError) && (
            <div className="auth-error">⚠️ {localError || error}</div>
          )}
          <button type="submit" className="btn btn-primary btn-wide" disabled={loading}>
            {loading ? 'Signing in…' : 'Log in'}
          </button>
        </form>
        <div className="auth-switch">
          New to Trade Stag? <Link to="/signup">Create an account</Link>
        </div>
      </div>
    </div>
  );
}

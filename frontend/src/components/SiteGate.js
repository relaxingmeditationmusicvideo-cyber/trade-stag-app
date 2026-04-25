import React, { useState, useEffect } from 'react';
import Logo from './Logo';

// Temporary site-wide password gate.
// To remove: delete this component and unwrap <SiteGate> from App.js
const SITE_HASH = 'b29ccaa6'; // lightweight hash of the password

function simpleHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return (h >>> 0).toString(16);
}

export default function SiteGate({ children }) {
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = sessionStorage.getItem('site_unlocked');
    if (stored === SITE_HASH) {
      setUnlocked(true);
    }
    setLoading(false);
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');
    if (simpleHash(password) === SITE_HASH) {
      sessionStorage.setItem('site_unlocked', SITE_HASH);
      setUnlocked(true);
    } else {
      setError('Incorrect password. Please try again.');
      setPassword('');
    }
  };

  if (loading) return null;
  if (unlocked) return children;

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0a0f1a 0%, #101828 50%, #0a0f1a 100%)',
      padding: 20,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      <div style={{
        maxWidth: 420,
        width: '100%',
        textAlign: 'center',
        background: 'rgba(16, 24, 40, 0.85)',
        borderRadius: 16,
        padding: '48px 32px',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
      }}>
        <div style={{ marginBottom: 24 }}>
          <Logo size={32} variant="full" />
        </div>
        <div style={{
          fontSize: 13,
          color: '#94a3b8',
          marginBottom: 8,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
        }}>
          Private Beta
        </div>
        <h1 style={{
          fontSize: 22,
          fontWeight: 700,
          color: '#f1f5f9',
          marginBottom: 8,
        }}>
          This site is password protected
        </h1>
        <p style={{
          color: '#64748b',
          fontSize: 14,
          lineHeight: 1.6,
          marginBottom: 28,
        }}>
          Enter the access password to continue.
        </p>

        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter site password"
            autoFocus
            style={{
              width: '100%',
              padding: '14px 16px',
              borderRadius: 10,
              border: error ? '1px solid #ef4444' : '1px solid rgba(255,255,255,0.12)',
              background: 'rgba(255,255,255,0.05)',
              color: '#f1f5f9',
              fontSize: 15,
              outline: 'none',
              boxSizing: 'border-box',
              marginBottom: 12,
              transition: 'border-color 0.2s',
            }}
            onFocus={(e) => {
              if (!error) e.target.style.borderColor = '#06b6d4';
            }}
            onBlur={(e) => {
              if (!error) e.target.style.borderColor = 'rgba(255,255,255,0.12)';
            }}
          />

          {error && (
            <div style={{
              color: '#ef4444',
              fontSize: 13,
              marginBottom: 12,
              fontWeight: 500,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            style={{
              width: '100%',
              padding: '14px 20px',
              borderRadius: 10,
              border: 'none',
              background: 'linear-gradient(135deg, #059669 0%, #06b6d4 100%)',
              color: '#fff',
              fontSize: 15,
              fontWeight: 700,
              cursor: 'pointer',
              transition: 'opacity 0.2s',
            }}
            onMouseEnter={(e) => e.target.style.opacity = '0.9'}
            onMouseLeave={(e) => e.target.style.opacity = '1'}
          >
            Enter Site
          </button>
        </form>

        <p style={{
          color: '#475569',
          fontSize: 11,
          marginTop: 24,
        }}>
          Trade Stag — NSE 500 Screener & Analysis Platform
        </p>
      </div>
    </div>
  );
}

import React from 'react';
import { useAuth } from '../AuthContext';

export default function PendingApproval() {
  const { logout } = useAuth();

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg1)',
      padding: 20,
    }}>
      <div style={{
        maxWidth: 480,
        textAlign: 'center',
        background: 'var(--bg2)',
        borderRadius: 16,
        padding: '48px 32px',
        border: '1px solid var(--border)',
      }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>⏳</div>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
          Account Pending Approval
        </h1>
        <p style={{ color: 'var(--muted)', lineHeight: 1.6, marginBottom: 24 }}>
          Thank you for signing up! Your account is currently awaiting admin approval.
          You'll receive an email once your access has been granted.
        </p>
        <div style={{
          background: 'rgba(212,160,36,0.1)',
          border: '1px solid rgba(212,160,36,0.25)',
          borderRadius: 8,
          padding: '12px 16px',
          marginBottom: 24,
          fontSize: 13,
          color: 'var(--amber)',
        }}>
          The admin has been notified of your signup and will review your request shortly.
        </div>
        <button
          onClick={logout}
          style={{
            padding: '10px 24px',
            borderRadius: 8,
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--text)',
            cursor: 'pointer',
            fontSize: 14,
          }}
        >
          Log out
        </button>
      </div>
    </div>
  );
}

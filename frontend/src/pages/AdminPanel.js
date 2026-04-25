import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../AuthContext';

export default function AdminPanel({ api }) {
  const { user, authFetch } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState('');

  const fetchUsers = useCallback(async () => {
    try {
      const res = await authFetch(`${api}/api/auth/admin/users`);
      if (res.ok) {
        const data = await res.json();
        setUsers(data.users || []);
      }
    } catch (e) {
      console.error('Failed to fetch users', e);
    } finally {
      setLoading(false);
    }
  }, [api, authFetch]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const handleApprove = async (userId, email) => {
    try {
      const res = await authFetch(`${api}/api/auth/admin/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      });
      if (res.ok) {
        setActionMsg(`Approved: ${email}`);
        fetchUsers();
      } else {
        const d = await res.json();
        setActionMsg(`Error: ${d.detail}`);
      }
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
    setTimeout(() => setActionMsg(''), 4000);
  };

  const handleReject = async (userId, email) => {
    try {
      const res = await authFetch(`${api}/api/auth/admin/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId }),
      });
      if (res.ok) {
        setActionMsg(`Rejected: ${email}`);
        fetchUsers();
      } else {
        const d = await res.json();
        setActionMsg(`Error: ${d.detail}`);
      }
    } catch (e) {
      setActionMsg(`Error: ${e.message}`);
    }
    setTimeout(() => setActionMsg(''), 4000);
  };

  if (!user?.is_owner) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <h2 style={{ color: 'var(--red)' }}>Access Denied</h2>
        <p className="text-muted">Only the admin can access this page.</p>
      </div>
    );
  }

  if (loading) return <div className="loading-spinner">Loading users...</div>;

  const pending = users.filter(u => !u.approved && !u.is_owner);
  const approved = users.filter(u => u.approved || u.is_owner);

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <h1 className="page-title">Admin Panel</h1>
      <p className="page-subtitle">Manage user access — approve or reject signups</p>

      {actionMsg && (
        <div style={{
          background: actionMsg.startsWith('Error') ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)',
          border: `1px solid ${actionMsg.startsWith('Error') ? 'var(--red)' : 'var(--green)'}`,
          borderRadius: 8, padding: '10px 16px', marginBottom: 16,
          color: actionMsg.startsWith('Error') ? 'var(--red)' : 'var(--green)',
          fontWeight: 600,
        }}>{actionMsg}</div>
      )}

      {/* Pending Approvals */}
      {pending.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 16, color: 'var(--amber)', marginBottom: 12 }}>
            Pending Approval ({pending.length})
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {pending.map(u => (
              <div key={u.id} className="card" style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '12px 16px', borderLeft: '3px solid var(--amber)',
              }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{u.email}</div>
                  <div className="text-xs text-muted">
                    {u.name || 'No name'} — Signed up: {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => handleApprove(u.id, u.email)}
                    style={{
                      padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
                      background: 'var(--green)', color: '#fff', fontWeight: 600, fontSize: 13,
                    }}
                  >Approve</button>
                  <button
                    onClick={() => handleReject(u.id, u.email)}
                    style={{
                      padding: '6px 16px', borderRadius: 6, border: '1px solid var(--red)', cursor: 'pointer',
                      background: 'transparent', color: 'var(--red)', fontWeight: 600, fontSize: 13,
                    }}
                  >Reject</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Approved Users */}
      <div>
        <h2 style={{ fontSize: 16, color: 'var(--green)', marginBottom: 12 }}>
          Approved Users ({approved.length})
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {approved.map(u => (
            <div key={u.id} className="card" style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 16px', borderLeft: u.is_owner ? '3px solid var(--cyan)' : '3px solid var(--green)',
            }}>
              <div>
                <div style={{ fontWeight: 700 }}>
                  {u.email}
                  {u.is_owner && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--cyan)', background: 'rgba(6,182,212,0.15)', padding: '2px 8px', borderRadius: 4 }}>OWNER</span>}
                </div>
                <div className="text-xs text-muted">
                  {u.name || 'No name'} — Last login: {u.last_login_at ? new Date(u.last_login_at).toLocaleDateString() : 'Never'}
                </div>
              </div>
              {!u.is_owner && (
                <button
                  onClick={() => handleReject(u.id, u.email)}
                  style={{
                    padding: '6px 12px', borderRadius: 6, border: '1px solid var(--red)', cursor: 'pointer',
                    background: 'transparent', color: 'var(--red)', fontWeight: 600, fontSize: 12,
                  }}
                >Revoke</button>
              )}
            </div>
          ))}
        </div>
      </div>

      {users.length === 0 && !loading && (
        <p className="text-muted" style={{ textAlign: 'center', padding: 20 }}>
          No users found.
        </p>
      )}
    </div>
  );
}

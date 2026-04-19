// Auth context — JWT token + plan status for subscription gating.
// Stores token in localStorage, user object (with plan info) in state.

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

const API = process.env.REACT_APP_API_URL || '';
const TOKEN_KEY = 'tradestag_token';
const USER_KEY = 'tradestag_user';

// Free plan: only these 3 scanners
export const FREE_SCANNERS = new Set(['all', 'aplus', 'trade']);

// Feature access checks
export function canAccessScanner(user, scannerId) {
  if (!user) return false;
  if (user.is_owner) return true;
  if (user.effective_plan === 'pro' || user.effective_plan === 'premium') return true;
  if (user.effective_plan === 'free') return FREE_SCANNERS.has(scannerId);
  return false; // expired
}

export function canAccessFeature(user, feature) {
  // feature: 'stock_detail', 'sectors', 'score_breakdown', 'csv_export', etc.
  if (!user) return false;
  if (user.is_owner) return true;
  if (user.effective_plan === 'premium') return true;
  if (user.effective_plan === 'pro') return true;
  // Free users get limited access
  if (user.effective_plan === 'free') {
    // Free users can see dashboard and basic market pulse
    if (feature === 'dashboard' || feature === 'market_pulse') return true;
    return false;
  }
  return false; // expired
}

export function isTrialExpired(user) {
  if (!user) return true;
  if (user.is_owner) return false;
  return user.trial_expired === true && user.plan === 'free';
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  });
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Persist
  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }, [token]);
  useEffect(() => {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  }, [user]);

  // Refresh user plan status on mount (and every 5 min)
  const refreshUser = useCallback(async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.user) setUser(data.user);
      } else if (res.status === 401) {
        // Token expired
        setToken(null);
        setUser(null);
      }
    } catch (e) {
      // Silently fail — user keeps cached data
    }
  }, [token]);

  useEffect(() => {
    refreshUser();
    const interval = setInterval(refreshUser, 5 * 60 * 1000); // refresh every 5 min
    return () => clearInterval(interval);
  }, [refreshUser]);

  const signup = useCallback(async ({ email, password, name }) => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Signup failed');
      setToken(data.token);
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      setError(e.message);
      return { ok: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async ({ email, password }) => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login failed');
      setToken(data.token);
      setUser(data.user);
      return { ok: true };
    } catch (e) {
      setError(e.message);
      return { ok: false, error: e.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const authFetch = useCallback((url, opts = {}) => {
    const headers = { ...(opts.headers || {}) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(url, { ...opts, headers });
  }, [token]);

  // Update user after plan change (e.g. after Razorpay payment)
  const updateUser = useCallback((newUser) => {
    setUser(newUser);
  }, []);

  return (
    <AuthContext.Provider value={{
      user, token, loading, error,
      signup, login, logout, authFetch,
      refreshUser, updateUser,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}

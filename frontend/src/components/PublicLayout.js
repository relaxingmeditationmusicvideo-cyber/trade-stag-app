import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import Footer from './Footer';
import Logo from './Logo';

export default function PublicLayout({ children }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  return (
    <div className="public-layout">
      <header className="public-header">
        <Link to="/" className="public-brand">
          <Logo size={24} variant="full" />
        </Link>
        <nav className="public-nav">
          <Link to="/" className={loc.pathname === '/' ? 'active' : ''}>Home</Link>
          <Link to="/pricing" className={loc.pathname === '/pricing' ? 'active' : ''}>Pricing</Link>
          <Link to="/disclaimer" className={loc.pathname === '/disclaimer' ? 'active' : ''}>Disclaimer</Link>
        </nav>
        <div className="public-auth-actions">
          {user ? (
            <>
              <Link to="/app" className="btn btn-primary">Go to App</Link>
              <button className="btn btn-ghost" onClick={logout}>Logout</button>
            </>
          ) : (
            <>
              <Link to="/login" className="btn btn-ghost">Log in</Link>
              <Link to="/signup" className="btn btn-primary">Sign up</Link>
            </>
          )}
        </div>
      </header>
      <main className="public-main">{children}</main>
      <Footer />
    </div>
  );
}

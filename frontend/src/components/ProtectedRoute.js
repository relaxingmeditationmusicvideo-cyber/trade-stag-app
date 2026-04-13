import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';

export default function ProtectedRoute({ children }) {
  const { user, token } = useAuth();
  const loc = useLocation();
  if (!user || !token) {
    return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  }
  return children;
}

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import PendingApproval from '../pages/PendingApproval';

export default function ProtectedRoute({ children }) {
  const { user, token } = useAuth();
  const loc = useLocation();

  if (!user || !token) {
    return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  }

  // If user is not approved and not the owner, show pending screen
  // (allow /app/admin route through for the owner)
  if (!user.approved && !user.is_owner && user.effective_plan === 'pending') {
    return <PendingApproval />;
  }

  return children;
}

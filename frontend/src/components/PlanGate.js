// PlanGate — Blocks access to features based on user plan.
// Shows upgrade prompt when user tries to access a locked feature.

import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth, canAccessScanner, canAccessFeature, isTrialExpired } from '../AuthContext';

// Inline upgrade prompt shown when feature is locked
export function UpgradePrompt({ feature, requiredPlan }) {
  const { user } = useAuth();
  const expired = isTrialExpired(user);

  return (
    <div className="upgrade-prompt">
      <div className="upgrade-prompt-icon">{expired ? '⏰' : '🔒'}</div>
      <h3 className="upgrade-prompt-title">
        {expired ? 'Your free trial has ended' : 'Upgrade to unlock this feature'}
      </h3>
      <p className="upgrade-prompt-desc">
        {expired
          ? 'Your 10-day free trial has expired. Upgrade to Pro or Premium to continue using Trade Stag.'
          : `This feature requires a ${requiredPlan || 'Pro'} plan or higher.`}
      </p>
      {user && user.is_trial && !expired && (
        <p className="upgrade-prompt-trial">
          Trial: <strong>{user.trial_days_left}</strong> day{user.trial_days_left !== 1 ? 's' : ''} remaining
        </p>
      )}
      <div className="upgrade-prompt-actions">
        <Link to="/pricing" className="btn btn-primary">View Plans</Link>
      </div>
    </div>
  );
}

// Gate for scanner access
export function ScannerGate({ scannerId, children }) {
  const { user } = useAuth();

  // Trial expired — block everything
  if (isTrialExpired(user)) {
    return <UpgradePrompt feature="scanner" requiredPlan="Pro" />;
  }

  // Check scanner access
  if (!canAccessScanner(user, scannerId)) {
    return <UpgradePrompt feature="scanner" requiredPlan="Pro" />;
  }

  return children;
}

// Gate for features (stock detail, sectors, etc.)
export function FeatureGate({ feature, requiredPlan, children }) {
  const { user } = useAuth();

  if (isTrialExpired(user)) {
    return <UpgradePrompt feature={feature} requiredPlan={requiredPlan || 'Pro'} />;
  }

  if (!canAccessFeature(user, feature)) {
    return <UpgradePrompt feature={feature} requiredPlan={requiredPlan || 'Pro'} />;
  }

  return children;
}

// Small banner shown at top for trial users
export function TrialBanner() {
  const { user } = useAuth();

  if (!user || user.is_owner) return null;
  if (user.effective_plan === 'pro' || user.effective_plan === 'premium') return null;

  const expired = isTrialExpired(user);

  return (
    <div className={`trial-banner ${expired ? 'expired' : ''}`}>
      {expired ? (
        <>
          <span>Your free trial has ended.</span>
          <Link to="/pricing" className="trial-banner-btn">Upgrade Now</Link>
        </>
      ) : (
        <>
          <span>Free trial: <strong>{user.trial_days_left}</strong> day{user.trial_days_left !== 1 ? 's' : ''} left</span>
          <Link to="/pricing" className="trial-banner-btn">Upgrade to Pro</Link>
        </>
      )}
    </div>
  );
}

// Badge for plan name in sidebar
export function PlanBadge() {
  const { user } = useAuth();
  if (!user) return null;

  const plan = user.is_owner ? 'Owner' : (user.effective_plan || 'free');
  const cls = plan === 'Owner' ? 'owner' : plan;

  return (
    <span className={`plan-badge plan-badge-${cls}`}>
      {plan === 'expired' ? 'Expired' : plan.charAt(0).toUpperCase() + plan.slice(1)}
    </span>
  );
}

export default ScannerGate;

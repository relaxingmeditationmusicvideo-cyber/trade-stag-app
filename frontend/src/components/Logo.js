import React from 'react';

/**
 * Trade Stag Logo — stylised stag antler that doubles as an upward chart line.
 * Works at any size via the `size` prop (default 28).
 * `variant`: "full" = icon + text,  "icon" = icon only,  "text" = text only.
 */
export default function Logo({ size = 28, variant = 'full', className = '' }) {
  const iconSize = size;
  const fontSize = size * 0.85;

  const icon = (
    <svg
      width={iconSize}
      height={iconSize}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="logo-icon"
    >
      {/* Gradient definitions */}
      <defs>
        <linearGradient id="antlerGrad" x1="8" y1="44" x2="40" y2="4" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#2dd4a0" />
          <stop offset="100%" stopColor="#d4a024" />
        </linearGradient>
        <linearGradient id="arrowGrad" x1="28" y1="40" x2="42" y2="8" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#2dd4a0" />
          <stop offset="100%" stopColor="#3be8b0" />
        </linearGradient>
      </defs>

      {/* Left antler branch — rising chart line */}
      <path
        d="M6 40 L14 28 L10 18 L8 8"
        stroke="url(#antlerGrad)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Left antler small tine */}
      <path
        d="M12 24 L6 18"
        stroke="url(#antlerGrad)"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />

      {/* Right antler branch — main uptrend */}
      <path
        d="M6 40 L18 30 L26 34 L36 14 L40 6"
        stroke="url(#arrowGrad)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Right antler small tine */}
      <path
        d="M32 20 L38 16"
        stroke="url(#arrowGrad)"
        strokeWidth="2.5"
        strokeLinecap="round"
        fill="none"
      />

      {/* Arrow tip at the top — bullish signal */}
      <path
        d="M36 6 L42 4 L40 10"
        stroke="#2dd4a0"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />

      {/* Small base dot — origin point */}
      <circle cx="6" cy="40" r="2.5" fill="url(#antlerGrad)" />
    </svg>
  );

  const text = (
    <span className="logo-text" style={{ fontSize }}>
      <span className="logo-trade">Trade</span>
      <span className="logo-stag">Stag</span>
    </span>
  );

  return (
    <span className={`logo-mark ${className}`}>
      {variant !== 'text' && icon}
      {variant !== 'icon' && text}
    </span>
  );
}

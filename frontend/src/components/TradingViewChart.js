import React, { memo, useMemo } from 'react';

/**
 * TradingView Chart — uses direct iframe embed (same approach as Chartink)
 * to load charts instantly without any notification/popup.
 *
 * Props:
 *   symbol   — NSE stock symbol (e.g. "RELIANCE")
 *   height   — chart height in px or '100%' (default 500)
 *   compact  — if true, uses smaller height and hides some toolbar items
 */
function TradingViewChart({ symbol, height = 500, compact = false }) {
  const src = useMemo(() => {
    const params = new URLSearchParams({
      symbol: `NSE:${symbol}`,
      interval: 'D',
      theme: 'dark',
      style: '1',
      locale: 'en',
      timezone: 'Asia/Kolkata',
      toolbar_bg: '#0a0c10',
      enable_publishing: '0',
      hide_top_toolbar: compact ? '1' : '0',
      hide_legend: '0',
      allow_symbol_change: compact ? '0' : '1',
      save_image: '0',
      hide_volume: '0',
      withdateranges: compact ? '0' : '1',
      hide_side_toolbar: '0',
      studies: compact ? '' : 'RSI@tv-basicstudies',
      utm_source: 'tradestag.com',
      utm_medium: 'widget',
    });
    return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
  }, [symbol, compact]);

  return (
    <div
      style={{
        height: height === '100%' ? '100%' : (compact ? 380 : height),
        width: '100%',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.08)',
        background: '#0a0c10',
      }}
    >
      <iframe
        title={`${symbol} chart`}
        src={src}
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          display: 'block',
        }}
        allowFullScreen
      />
    </div>
  );
}

export default memo(TradingViewChart);

import React, { useEffect, useRef, memo } from 'react';

/**
 * TradingView Advanced Chart Widget — embeds a full interactive chart
 * with candlesticks, volume, and 100+ indicators users can add.
 *
 * Props:
 *   symbol   — NSE stock symbol (e.g. "RELIANCE")
 *   height   — chart height in px (default 500)
 *   compact  — if true, uses smaller height and hides some toolbar items
 */
function TradingViewChart({ symbol, height = 500, compact = false }) {
  const containerRef = useRef(null);
  const scriptRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current || !symbol) return;

    // Clean previous widget
    containerRef.current.innerHTML = '';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.height = '100%';
    widgetDiv.style.width = '100%';
    containerRef.current.appendChild(widgetDiv);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `NSE:${symbol}`,
      interval: 'D',
      timezone: 'Asia/Kolkata',
      theme: 'dark',
      style: '1',
      locale: 'en',
      backgroundColor: 'rgba(10, 12, 16, 1)',
      gridColor: 'rgba(255, 255, 255, 0.04)',
      hide_top_toolbar: compact,
      hide_legend: false,
      allow_symbol_change: !compact,
      save_image: false,
      calendar: false,
      hide_volume: false,
      support_host: 'https://www.tradingview.com',
      studies: compact ? [] : ['RSI@tv-basicstudies'],
      withdateranges: !compact,
    });
    containerRef.current.appendChild(script);
    scriptRef.current = script;

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [symbol, compact]);

  return (
    <div
      className="tradingview-widget-container"
      ref={containerRef}
      style={{
        height: height === '100%' ? '100%' : (compact ? 380 : height),
        width: '100%',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.08)',
        background: '#0a0c10',
      }}
    />
  );
}

export default memo(TradingViewChart);

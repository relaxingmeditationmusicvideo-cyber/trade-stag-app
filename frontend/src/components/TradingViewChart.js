import React, { useEffect, useRef, memo } from 'react';

/**
 * TradingView Chart Widget — uses TradingView.widget() constructor
 * which loads charts directly without promotional popups.
 *
 * Props:
 *   symbol   — NSE stock symbol (e.g. "RELIANCE")
 *   height   — chart height in px or '100%' (default 500)
 *   compact  — if true, uses smaller height and hides some toolbar items
 */
function TradingViewChart({ symbol, height = 500, compact = false }) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef('tv_chart_' + Math.random().toString(36).slice(2, 10));

  useEffect(() => {
    if (!containerRef.current || !symbol) return;

    // Clear previous content
    containerRef.current.innerHTML = '';

    // Create target div for the widget
    const targetDiv = document.createElement('div');
    targetDiv.id = widgetIdRef.current;
    targetDiv.style.height = '100%';
    targetDiv.style.width = '100%';
    containerRef.current.appendChild(targetDiv);

    // Load TradingView library and create widget
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (window.TradingView && containerRef.current) {
        new window.TradingView.widget({
          container_id: widgetIdRef.current,
          autosize: true,
          symbol: `NSE:${symbol}`,
          interval: 'D',
          timezone: 'Asia/Kolkata',
          theme: 'dark',
          style: '1',
          locale: 'en',
          toolbar_bg: '#0a0c10',
          enable_publishing: false,
          hide_top_toolbar: compact,
          hide_legend: false,
          allow_symbol_change: !compact,
          save_image: false,
          hide_volume: false,
          studies: compact ? [] : ['RSI@tv-basicstudies'],
          withdateranges: !compact,
          backgroundColor: '#0a0c10',
          gridColor: 'rgba(255, 255, 255, 0.04)',
        });
      }
    };
    document.head.appendChild(script);

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

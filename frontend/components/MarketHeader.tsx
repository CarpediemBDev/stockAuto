'use client';

import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';
import { useMarketOverview, type MarketQuote } from '@/hooks/useMarketOverview';
import { getProfitColor, getRegimeTheme } from '@/lib/theme';

const MarketHeader = () => {
  // 국면·시세 조회는 useMarketOverview 훅이 SSOT다(중복 useSWR/타입 선언 금지).
  const { data: marketData, isLoading } = useMarketOverview();
  const data = marketData || null;

  if (isLoading && !data) return <div className="h-14 bg-surface-card/80 border-b border-zinc-800/80 animate-pulse"></div>;
  if (!data) return <div className="h-14 bg-surface-card/80 border-b border-zinc-800/80"></div>;
  const marketCondition = data.market_condition ?? data.sentiment;
  const regimeTheme = getRegimeTheme(marketCondition);

  const renderValue = (item: MarketQuote | null, label: string, icon: React.ReactNode) => {
    if (!item) return null;
    const isUp = item.change >= 0;
    const profitColor = getProfitColor(item.change);
    
    return (
      <div className="flex items-center space-x-3 px-6 border-r border-zinc-800/80 last:border-r-0">
        <div className="p-1.5 bg-zinc-800/50 rounded-full text-zinc-400">
          {icon}
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider mb-0.5">{label}</span>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-bold text-slate-200">{item.current.toLocaleString()}</span>
            <span className={`text-[11px] font-medium flex items-center ${profitColor}`}>
              {isUp ? '+' : ''}{item.change.toLocaleString()} ({isUp ? '+' : ''}{item.change_pct}%)
              {isUp ? <TrendingUp size={12} className="ml-0.5" /> : <TrendingDown size={12} className="ml-0.5" />}
            </span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full bg-surface-card/80 backdrop-blur-md border-b border-zinc-800/80 sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto h-14 flex items-center justify-between px-6">
        <div className="flex items-center">
          {renderValue(data.nasdaq, 'NASDAQ', <Activity size={14} />)}
          {renderValue(data.exchange_rate, 'USD / KRW', <DollarSign size={14} />)}
        </div>
        
        <div className="flex items-center space-x-2">
          <div className={`px-4 py-1.5 rounded-full text-[11px] font-bold tracking-tight border flex items-center space-x-2 ${regimeTheme.badgeClass}`}>
            <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${regimeTheme.dotColor}`}></div>
            <span className="uppercase">Market {regimeTheme.label}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketHeader;

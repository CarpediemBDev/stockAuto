'use client';

import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react';
import useSWR from 'swr';
import { fetcher } from '@/lib/api';

interface MarketData {
  symbol: string;
  current: number;
  change: number;
  change_pct: number;
}

interface MarketOverview {
  market_condition?: string;
  sentiment: string;
  nasdaq: MarketData | null;
  exchange_rate: MarketData | null;
}

const MarketHeader = () => {
  const { data: marketData, isLoading } = useSWR('/market/overview', fetcher, { refreshInterval: 15000 });
  const data: MarketOverview | null = marketData || null;

  if (isLoading && !data) return <div className="h-14 bg-[#0f172a] border-b border-slate-800 animate-pulse"></div>;
  if (!data) return <div className="h-14 bg-[#0f172a] border-b border-slate-800"></div>;
  const marketCondition = data.market_condition ?? data.sentiment;

  const renderValue = (item: MarketData | null, label: string, icon: React.ReactNode) => {
    if (!item) return null;
    const isUp = item.change >= 0;
    
    return (
      <div className="flex items-center space-x-3 px-6 border-r border-slate-800 last:border-r-0">
        <div className="p-1.5 bg-slate-800/50 rounded-full text-slate-400">
          {icon}
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] text-slate-500 font-medium uppercase tracking-wider mb-0.5">{label}</span>
          <div className="flex items-center space-x-2">
            <span className="text-sm font-bold text-slate-200">{item.current.toLocaleString()}</span>
            <span className={`text-[11px] font-medium flex items-center ${isUp ? 'text-rose-500' : 'text-blue-500'}`}>
              {isUp ? '+' : ''}{item.change.toLocaleString()} ({isUp ? '+' : ''}{item.change_pct}%)
              {isUp ? <TrendingUp size={12} className="ml-0.5" /> : <TrendingDown size={12} className="ml-0.5" />}
            </span>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="w-full bg-[#0f172a]/80 backdrop-blur-md border-b border-slate-800 sticky top-0 z-50">
      <div className="max-w-[1600px] mx-auto h-14 flex items-center justify-between px-6">
        <div className="flex items-center">
          {renderValue(data.nasdaq, 'NASDAQ', <Activity size={14} />)}
          {renderValue(data.exchange_rate, 'USD / KRW', <DollarSign size={14} />)}
        </div>
        
        <div className="flex items-center space-x-2">
          <div className={`px-4 py-1.5 rounded-full text-[11px] font-bold tracking-tight border flex items-center space-x-2
            ${marketCondition === 'BULLISH' ? 'bg-rose-500/10 text-rose-500 border-rose-500/20' : 
              marketCondition === 'BEARISH' ? 'bg-blue-500/10 text-blue-500 border-blue-500/20' : 
              'bg-slate-500/10 text-slate-400 border-slate-500/20'}`}>
            <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${marketCondition === 'BULLISH' ? 'bg-rose-500' : marketCondition === 'BEARISH' ? 'bg-blue-500' : 'bg-slate-400'}`}></div>
            <span className="uppercase">Market {marketCondition}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketHeader;

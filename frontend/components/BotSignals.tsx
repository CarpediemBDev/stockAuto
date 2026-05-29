'use client';

import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import { scannerAPI, isCancel } from '@/lib/api';

import { usePolling } from '@/hooks/usePolling';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

interface Signal {
  ticker: string;
  name: string;
  price: number;
  signal_score: number;
  reason?: string;
  rsi?: number;
  rvol?: number;
}
interface BotSignalsProps {
  hideHeader?: boolean;
}

const BotSignals: React.FC<BotSignalsProps> = ({ hideHeader = false }) => {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSignals = React.useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await scannerAPI.getLatest({ signal });
      setSignals(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error('Failed to fetch bot signals:', msg);
      toast.error(`시그널 갱신 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchSignals, 30000);

  if (loading) return <div className="h-64 bg-slate-900/50 rounded-2xl animate-pulse"></div>;

  return (
    <div className={hideHeader ? "" : "bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden"}>
      {!hideHeader && (
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div className="flex items-center space-x-2">
            <Zap size={16} className="text-amber-400" />
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">{"Bot's Detected Signals"}</h3>
          </div>
          <span className="text-[10px] text-slate-500 font-mono italic text-rose-400 animate-pulse">LIVE SCANNING...</span>
        </div>
      )}
      
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800/50 text-[11px] uppercase tracking-tighter">
              <th className="px-5 py-3 font-semibold">Ticker</th>
              <th className="px-2 py-3 font-semibold">Price</th>
              <th className="px-2 py-3 font-semibold text-center">Score</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/30">
            {signals.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-10 text-center text-slate-600 italic">No signals detected yet.</td>
              </tr>
            ) : (
              signals.map((s) => (
                <tr key={s.ticker} className="hover:bg-slate-800/30 transition-colors group">
                  <td className="px-5 py-3">
                    <div className="flex flex-col">
                      <span className="font-bold text-slate-200">{s.ticker}</span>
                      <span className="text-[10px] text-slate-500 truncate max-w-[100px]">{s.name}</span>
                    </div>
                  </td>
                  <td className="px-2 py-3 font-mono text-slate-300">${s.price.toFixed(2)}</td>
                  <td className="px-2 py-3">
                    <div className="flex justify-center">
                      <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center text-[12px] font-black
                        ${s.signal_score >= 80 ? 'border-rose-500 text-rose-500 bg-rose-500/5' : 
                          s.signal_score >= 60 ? 'border-amber-500 text-amber-500' : 'border-slate-700 text-slate-500'}`}>
                        {s.signal_score}
                      </div>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default BotSignals;

'use client';

import React, { useState, useCallback } from 'react';
import { Target, ArrowUpRight, ArrowDownRight, ShieldAlert } from 'lucide-react';
import { accountAPI, isCancel } from '@/lib/api';
import { usePolling } from '@/hooks/usePolling';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

interface Holding {
  id: number;
  ticker: string;
  ticker_name: string;
  avg_price: number;
  quantity: number;
  highest_price: number;
}

const PortfolioView = () => {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchHoldings = React.useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await accountAPI.getHoldings({ signal });
      setHoldings(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error('Failed to fetch holdings:', msg);
      toast.error(`포트폴리오 갱신 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchHoldings, 30000);

  if (loading) return <div className="text-slate-500 text-sm p-8 text-center animate-pulse">Loading portfolio...</div>;

  if (holdings.length === 0) {
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-12 text-center">
        <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
          <Target className="text-slate-600" size={32} />
        </div>
        <h3 className="text-lg font-bold text-slate-300">보유 종목이 없습니다</h3>
        <p className="text-slate-500 text-sm mt-2">봇이 시그널을 감시하며 매수 기회를 찾고 있습니다.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {holdings.map((h) => {
        // 실제 운영 시에는 현재가를 API에서 따로 받아오거나 
        // Holdings에 현재가를 포함시켜야 하지만, 여기선 예시로 수익률 0% 기준 시각화
        const currentPrice = h.avg_price * 1.02; // 예시: 2% 수익 중
        const profitRate = ((currentPrice - h.avg_price) / h.avg_price) * 100;
        const trailingLine = h.highest_price * 0.98; // 최고가 대비 -2% 라인
        const dropFromPeak = ((currentPrice - h.highest_price) / h.highest_price) * 100;
        const distToExit = ((currentPrice - trailingLine) / currentPrice) * 100;

        return (
          <div key={h.id} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all group">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h4 className="text-xs font-bold text-slate-500 tracking-wider uppercase">{h.ticker}</h4>
                <h3 className="text-base font-bold text-slate-100">{h.ticker_name}</h3>
              </div>
              <div className={`flex items-center px-2 py-1 rounded text-xs font-bold ${profitRate >= 0 ? 'bg-rose-500/10 text-rose-500' : 'bg-blue-500/10 text-blue-500'}`}>
                {profitRate >= 0 ? <ArrowUpRight size={14} className="mr-1" /> : <ArrowDownRight size={14} className="mr-1" />}
                {profitRate.toFixed(2)}%
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">평단가</span>
                <span className="text-slate-300 font-mono">${h.avg_price.toLocaleString()}</span>
              </div>
              
              {/* 트레일링 스탑 게이지 */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-[10px] font-bold tracking-tight">
                  <span className="text-slate-500">TRAILING STOP LINE (-2% from peak)</span>
                  <span className={distToExit < 0.5 ? 'text-amber-500' : 'text-slate-400'}>
                    EXIT IN {distToExit.toFixed(2)}%
                  </span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className={`h-full transition-all duration-500 ${distToExit < 0.5 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                    style={{ width: `${Math.max(0, Math.min(100, (1 - Math.abs(dropFromPeak)/2) * 100))}%` }}
                  ></div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-800/50">
                <div className="flex flex-col">
                  <span className="text-[10px] text-slate-500 uppercase">최고가(Peak)</span>
                  <span className="text-sm font-bold text-slate-300">${h.highest_price.toLocaleString()}</span>
                </div>
                {distToExit < 0.5 && (
                  <div className="flex items-center text-amber-500 animate-pulse">
                    <ShieldAlert size={16} className="mr-1" />
                    <span className="text-[11px] font-bold">탈출 준비</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default PortfolioView;

'use client';

import React, { useState, useCallback } from 'react';
import { Target, ArrowUpRight, ArrowDownRight, ShieldAlert, Info } from 'lucide-react';
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
  current_price?: number;
  is_mock?: boolean;
  provider?: string;
  fx_rate?: number;
}

const PortfolioView = ({ displayCurrency = "KRW" }: { displayCurrency?: "KRW" | "USD" }) => {
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
        // 백엔드에서 실시간으로 조회한 현재가를 적용하고, 없을 경우 폴백값 설정
        const currentPrice = h.current_price !== undefined ? h.current_price : h.avg_price * 1.02;
        const profitRate = ((currentPrice - h.avg_price) / h.avg_price) * 100;
        const trailingLine = h.highest_price * 0.98; // 최고가 대비 -2% 라인
        const dropFromPeak = ((currentPrice - h.highest_price) / h.highest_price) * 100;
        const distToExit = ((currentPrice - trailingLine) / currentPrice) * 100;

        return (
          <div key={h.id} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all group flex flex-col h-full">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h4 className="text-xs font-bold text-slate-500 tracking-wider uppercase flex items-center gap-1.5">
                  {h.ticker}
                  <span className={`text-[8px] font-black px-1 py-0.5 rounded border tracking-wider uppercase ${
                    h.is_mock === false
                      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                      : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                  }`}>
                    {h.provider || (h.is_mock === false ? "Live" : "Mock")}
                  </span>
                </h4>
                <div className="flex items-baseline gap-2 mt-0.5">
                  <h3 className="text-base font-bold text-slate-100">{h.ticker_name}</h3>
                  <span className={`text-xs font-bold font-mono ${profitRate >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
                    {displayCurrency === "USD"
                      ? `$${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                      : `${(h.fx_rate ? currentPrice * h.fx_rate : currentPrice * 1350).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
                    }
                  </span>
                </div>
              </div>
              <div className={`flex items-center px-2 py-1 rounded text-xs font-bold ${profitRate >= 0 ? 'bg-rose-500/10 text-rose-500' : 'bg-blue-500/10 text-blue-500'}`}>
                {profitRate >= 0 ? <ArrowUpRight size={14} className="mr-1" /> : <ArrowDownRight size={14} className="mr-1" />}
                {profitRate.toFixed(2)}%
              </div>
            </div>

            <div className="space-y-4 flex flex-col flex-grow justify-between">
              <div>
                {/* 핵심 투자 지표 */}
                <div className="grid grid-cols-2 gap-2 p-3 bg-slate-950/60 rounded-xl border border-slate-800/40 text-xs">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">평단가</span>
                    <span className="text-slate-200 font-mono font-medium">
                      {displayCurrency === "USD"
                        ? `$${h.avg_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : `${(h.fx_rate ? h.avg_price * h.fx_rate : h.avg_price * 1350).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
                      }
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5 text-right">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">보유 수량</span>
                    <span className="text-slate-200 font-mono font-medium">{h.quantity.toLocaleString()}주</span>
                  </div>
                  <div className="flex flex-col gap-0.5 mt-1.5 pt-1.5 border-t border-slate-800/40">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">투자 원금</span>
                    <span className="text-slate-400 font-mono font-medium">
                      {displayCurrency === "USD"
                        ? `$${(h.avg_price * h.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : `${((h.avg_price * h.quantity) * (h.fx_rate || 1350)).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
                      }
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5 text-right mt-1.5 pt-1.5 border-t border-slate-800/40">
                    <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">평가 금액</span>
                    <span className={`font-mono font-bold ${profitRate >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
                      {displayCurrency === "USD"
                        ? `$${(currentPrice * h.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                        : `${((currentPrice * h.quantity) * (h.fx_rate || 1350)).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
                      }
                    </span>
                  </div>
                </div>
                
                {/* 트레일링 스탑 게이지 */}
                <div className="space-y-1.5 mt-4">
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
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-800/50 mt-6">
                <div className="flex flex-col">
                  <span className="group/tip relative inline-flex items-center gap-1 cursor-help text-[10px] text-slate-500 uppercase select-none w-fit">
                    <span>최고가(Peak)</span>
                    <Info size={10} className="text-slate-600 group-hover/tip:text-slate-400 transition-colors" />
                    <span className="pointer-events-none absolute bottom-full left-0 mb-2 w-64 scale-95 opacity-0 group-hover/tip:scale-100 group-hover/tip:opacity-100 transition-all duration-200 bg-slate-950 text-slate-400 text-[9px] font-normal normal-case leading-relaxed p-2.5 rounded-lg shadow-2xl border border-slate-800 z-50 text-left whitespace-normal">
                      매수 평단가로 최초 시작(초기화)되며, 주가가 상승하면 최고가로 자동 갱신됩니다. 최고가가 평단가를 초과한 이력이 있어야만 익절(트레일링 스탑) 비상탈출 시스템이 활성화됩니다.
                    </span>
                  </span>
                  <span className="text-sm font-bold text-slate-300">
                    {displayCurrency === "USD"
                      ? `$${h.highest_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                      : `${(h.fx_rate ? h.highest_price * h.fx_rate : h.highest_price * 1350).toLocaleString(undefined, { maximumFractionDigits: 0 })}원`
                    }
                  </span>
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

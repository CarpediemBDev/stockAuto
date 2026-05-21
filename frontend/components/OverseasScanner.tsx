"use client";

import React, { useState, useCallback } from "react";
import { Radar, RefreshCw, TrendingUp, Plus, Zap, Eye, Minus, Info } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { scannerAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";

interface ScanResult {
  ticker: string;
  name: string;
  price: number;
  signal_score: number;
  signal_type: "STRONG_BUY" | "BUY" | "WATCH" | "NEUTRAL";
    details: {
    gap: number;
    rvol: number;
    wick: number;
    has_news: boolean;
    risk: "LOW" | "MEDIUM" | "HIGH";
    rs: number;
    ema_aligned: boolean;
  };
}

const SIGNAL_CONFIG = {
  STRONG_BUY: { label: "STRONG BUY", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30", icon: Zap },
  BUY:        { label: "BUY",        color: "text-amber-400", bg: "bg-amber-500/15 border-amber-500/30", icon: TrendingUp },
  WATCH:      { label: "WATCH",      color: "text-blue-400",  bg: "bg-blue-500/15 border-blue-500/30",  icon: Eye },
  NEUTRAL:    { label: "NEUTRAL",    color: "text-zinc-500",  bg: "bg-zinc-500/10 border-zinc-700/30",  icon: Minus },
};

// 프리미엄 마켓 스캐너 툴팁 설명 가이드 컴포넌트
interface HeaderTooltipProps {
  title: string;
  desc: string;
}
function HeaderTooltip({ title, desc }: HeaderTooltipProps) {
  return (
    <span className="group/tip relative inline-flex items-center gap-1 cursor-help justify-center">
      <span className="font-semibold text-zinc-500 group-hover/tip:text-zinc-300 transition-colors">{title}</span>
      <Info size={11} className="text-zinc-600 group-hover/tip:text-zinc-400 transition-colors" />
      <span className="pointer-events-none absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 scale-90 opacity-0 group-hover/tip:scale-100 group-hover/tip:opacity-100 transition-all duration-200 bg-zinc-950 text-zinc-300 text-[10px] font-normal leading-relaxed p-2.5 rounded-lg shadow-xl border border-zinc-850 z-50 text-left normal-case whitespace-normal">
        {desc}
      </span>
    </span>
  );
}

interface OverseasScannerProps {
  onAddToWatchlist?: (ticker: string, name: string) => void;
  watchlistTickers?: string[];
}

export function OverseasScanner({ onAddToWatchlist, watchlistTickers = [] }: OverseasScannerProps) {
  const [results, setResults] = useState<ScanResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [isSpinning, setIsSpinning] = useState(false);

  const fetchScan = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setIsSpinning(true);
    try {
      const res = await scannerAPI.getLatest({ signal });
      setResults(res.data);
      setLastUpdated(new Date());
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error("Failed to fetch overseas scan results:", msg);
      toast.error(`스캐너 데이터 갱신 실패: ${msg}`);
    } finally {
      setIsLoading(false);
      setTimeout(() => setIsSpinning(false), 1000); // 최소 1초 동안 스핀 애니메이션 유지
    }
  }, []);

  usePolling(fetchScan, 30000);

  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl shadow-xl flex flex-col h-full overflow-hidden">
      {/* 헤더 */}
      <div className="flex items-center justify-between p-5 border-b border-zinc-800/80">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
            <Radar size={22} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-tight">Market Scanner</h2>
            <p className="text-zinc-500 text-xs font-medium">실시간 전수 조사 (Gap, News, RVOL, RS)</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-[11px] text-zinc-600 font-mono">
              Last update: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => fetchScan()}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-medium transition-all active:scale-95 disabled:opacity-50"
          >
            <RefreshCw size={13} className={cn(isSpinning && "animate-spin text-indigo-400")} />
            {isLoading ? "Scanning..." : "Rescan"}
          </button>
        </div>
      </div>

      {/* 테이블 영역 */}
      <div className="flex-1 overflow-y-auto no-scrollbar">
        {isLoading && results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            <Radar size={40} className="animate-ping mb-4 opacity-20 text-indigo-500" />
            <p className="text-sm font-medium">시장 전체 데이터를 필터링하고 있습니다...</p>
            <p className="text-xs text-zinc-600 mt-2">Stage 1: 15분봉 벌크 스캔 중 (7,000+ Tickers)</p>
          </div>
        ) : results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            <Zap size={30} className="mb-3 opacity-20" />
            <p className="text-sm">현재 시그널이 포착된 종목이 없습니다.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-zinc-800/50 text-zinc-500 text-[10px] uppercase tracking-[0.1em]">
                <th className="py-4 px-5 font-semibold">Rank</th>
                <th className="py-4 px-2 font-semibold">Ticker / Name</th>
                <th className="py-4 px-4 font-semibold text-right">Price</th>
                <th className="py-4 px-4 font-semibold text-center">
                  <HeaderTooltip title="Gap / RVOL" desc="Gap: 전일 종가 대비 시가의 갭 상승비율. RVOL: 최근 20일 평균 대비 현재 거래량 비율 (2.0배 돌파 시 강세)." />
                </th>
                <th className="py-4 px-4 font-semibold text-center">
                  <HeaderTooltip title="Trend / RS" desc="Trend: EMA(9/20일 이평선) 정배열 상승 상태. RS: QQQ 지수 대비 실시간 초과수익 성향 (시장 극복 지표)." />
                </th>
                <th className="py-4 px-4 font-semibold text-center">
                  <HeaderTooltip title="Risk / Wick" desc="Risk: 고점 윗꼬리에 따른 물림 위험도. Wick: 1분봉 캔들의 윗꼬리 비율 (30% 이하인 꽉 찬 몸통이 안전)." />
                </th>
                <th className="py-4 px-4 font-semibold text-center">
                  <HeaderTooltip title="Signal Score" desc="시장 추세, 거래량, 갭, 정배열, 윗꼬리, 뉴스 등 6대 핵심 지표를 종합 합산한 추천 점수 (80점 이상 STRONG BUY)." />
                </th>
                <th className="py-4 px-5 font-semibold text-right w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/30">
              {results.map((item, idx) => {
                const signal = SIGNAL_CONFIG[item.signal_type] || SIGNAL_CONFIG.NEUTRAL;
                const SignalIcon = signal.icon;
                const isInWatchlist = watchlistTickers.includes(item.ticker);
                const d = item.details;

                return (
                  <tr
                    key={item.ticker}
                    className={cn(
                      "group hover:bg-white/[0.02] transition-all",
                      idx === 0 && "bg-indigo-500/[0.02]"
                    )}
                  >
                    {/* 순위 */}
                    <td className="py-4 px-5">
                      <span className="text-zinc-600 font-mono text-xs">{String(idx + 1).padStart(2, '0')}</span>
                    </td>

                    {/* 종목 정보 */}
                    <td className="py-4 px-2">
                      <div className="flex items-center gap-2">
                        <div className="flex flex-col">
                          <span className="text-white font-bold text-sm tracking-tight">{item.name}</span>
                          <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-wider">{item.ticker}</span>
                        </div>
                        {d.has_news && (
                          <span className="flex h-5 items-center px-1.5 rounded bg-amber-500/10 text-amber-500 text-[9px] font-bold border border-amber-500/20 animate-pulse">
                            NEWS 🔥
                          </span>
                        )}
                      </div>
                    </td>

                    {/* 가격 */}
                    <td className="py-4 px-4 text-right">
                      <span className="text-zinc-200 font-mono text-sm font-semibold">
                        ${item.price.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                    </td>

                    {/* Gap / RVOL */}
                    <td className="py-4 px-4">
                      <div className="flex flex-col items-center gap-1">
                        <div className="flex items-center gap-1.5">
                          <span className={cn(
                            "text-[11px] font-bold px-1.5 py-0.5 rounded",
                            d.gap > 0 ? "bg-rose-500/10 text-rose-400" : "bg-blue-500/10 text-blue-400"
                          )}>
                            {d.gap > 0 ? '+' : ''}{d.gap}%
                          </span>
                          <span className={cn(
                            "text-[11px] font-mono font-medium",
                            d.rvol >= 2.0 ? "text-amber-400" : "text-zinc-500"
                          )}>
                            {d.rvol.toFixed(1)}x
                          </span>
                        </div>
                        <div className="w-16 h-1 bg-zinc-800 rounded-full overflow-hidden">
                          <div 
                            className={cn("h-full transition-all duration-1000", d.rvol >= 2.0 ? "bg-amber-500" : "bg-indigo-500")}
                            style={{ width: `${Math.min(100, d.rvol * 20)}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Trend / RS */}
                    <td className="py-4 px-4">
                      <div className="flex flex-col items-center gap-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className={cn(
                            "text-[9px] px-1.5 py-0.5 rounded font-bold border",
                            d.ema_aligned ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" : "bg-zinc-500/10 text-zinc-500 border-zinc-700/30"
                          )}>
                            {d.ema_aligned ? "UPTREND" : "SIDEWAYS"}
                          </span>
                          <span className={cn(
                            "text-[10px] font-mono font-bold",
                            d.rs > 0 ? "text-indigo-400" : "text-zinc-500"
                          )}>
                            RS {d.rs > 0 ? '+' : ''}{d.rs.toFixed(1)}
                          </span>
                        </div>
                        <div className="w-16 h-1 bg-zinc-800 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-indigo-500 transition-all duration-1000" 
                            style={{ width: `${Math.min(100, Math.max(0, (d.rs + 5) * 10))}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    {/* Risk / Wick */}
                    <td className="py-4 px-4">
                      <div className="flex flex-col items-center gap-1.5">
                        <span className={cn(
                          "text-[9px] px-1.5 py-0.5 rounded-full font-bold border",
                          d.risk === "LOW" ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20" :
                          d.risk === "HIGH" ? "bg-rose-500/10 text-rose-500 border-rose-500/20 animate-bounce" :
                          "bg-amber-500/10 text-amber-500 border-amber-500/20"
                        )}>
                          {d.risk} RISK
                        </span>
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] text-zinc-500 font-medium">Wick: {(d.wick * 100).toFixed(0)}%</span>
                          {d.wick >= 0.5 && <Zap size={10} className="text-rose-500 fill-rose-500" />}
                        </div>
                      </div>
                    </td>

                    {/* 시그널 점수 */}
                    <td className="py-4 px-4 text-center">
                      <div className="flex flex-col items-center gap-1.5">
                        <div className={cn(
                          "flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[10px] font-black tracking-widest transition-all group-hover:scale-105",
                          signal.bg, signal.color
                        )}>
                          <SignalIcon size={12} strokeWidth={3} />
                          {signal.label}
                        </div>
                        <div className="flex items-center gap-2">
                           <div className="w-20 h-1.5 bg-zinc-800 rounded-full overflow-hidden shadow-inner">
                            <div 
                              className={cn("h-full transition-all duration-1000 shadow-[0_0_8px_rgba(0,0,0,0.5)]", 
                                item.signal_score >= 80 ? "bg-rose-500" : 
                                item.signal_score >= 60 ? "bg-amber-500" : "bg-blue-500"
                              )}
                              style={{ width: `${item.signal_score}%` }}
                            />
                          </div>
                          <span className="text-[10px] text-zinc-400 font-mono font-bold">{item.signal_score}</span>
                        </div>
                      </div>
                    </td>

                    {/* 액션 */}
                    <td className="py-4 px-5 text-right">
                      {isInWatchlist ? (
                        <div className="flex justify-end pr-1">
                          <div className="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-500">
                            <Plus size={14} className="rotate-45" />
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={() => onAddToWatchlist?.(item.ticker, item.name)}
                          className="w-8 h-8 rounded-full bg-zinc-800 hover:bg-indigo-500/20 hover:text-indigo-400 flex items-center justify-center text-zinc-500 transition-all active:scale-90"
                          title="관심종목 추가"
                        >
                          <Plus size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 푸터 정보 */}
      <div className="px-5 py-3 bg-white/[0.01] border-t border-zinc-800/50 flex justify-between items-center">
        <div className="flex items-center gap-4 text-[10px] text-zinc-600 font-medium">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-rose-500" />
            <span>Gap UP</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            <span>High RVOL</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
            <span>Trend Aligned</span>
          </div>
        </div>
        <div className="text-[10px] text-zinc-500 italic">
          * Signals are based on Multi-Timeframe Analysis
        </div>
      </div>
    </div>
  );
}

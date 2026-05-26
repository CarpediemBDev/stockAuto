"use client";

import React, { useState, useCallback } from "react";
import { 
  Radar, 
  RefreshCw, 
  TrendingUp, 
  Plus, 
  Zap, 
  Eye, 
  Minus, 
  Info, 
  ChevronDown, 
  ExternalLink, 
  Activity, 
  MessageSquare 
} from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { scannerAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";

interface ScoreCardFactor {
  factor: string;
  score: number;
  passed: boolean;
}

interface ScanResult {
  ticker: string;
  name: string;
  price: number;
  signal_score: number;
  signal_type: "STRONG_BUY" | "BUY" | "WATCH" | "NEUTRAL";
  news_sentiment?: "POSITIVE" | "NEGATIVE" | "NEUTRAL";
  news_sentiment_score?: number;
  news_summary?: string;
  news_url?: string;
  patterns?: string[];
  score_card?: ScoreCardFactor[];
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

// VCP 패턴 SVG 드로잉 블루프린트 아이콘
function VCPSvgIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-indigo-400 mr-1 animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 12c3-6 6 3 9-3 2 4 4-2 6 2 1-1 2-1 3-1" />
      <path d="M12 3v18" strokeDasharray="2 2" className="opacity-30" />
    </svg>
  );
}

// 컵앤핸들 패턴 SVG 드로잉 블루프린트 아이콘
function CupAndHandleSvgIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-amber-400 mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 8c0 6 3 10 8 10s8-4 8-10" />
      <path d="M20 10c2.5 0 2.5 4 0 4" />
    </svg>
  );
}

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
  
  // 아코디언 확장 티커 상태 관리
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  // AI 뉴스 상세 보기 모달 상태 관리
  const [selectedNewsItem, setSelectedNewsItem] = useState<ScanResult | null>(null);

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
      {/* 아코디언 및 미세 스펙트럼 슬라이드 애니메이션 인라인 주입 */}
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-8px); max-height: 0; }
          to { opacity: 1; transform: translateY(0); max-height: 600px; }
        }
        .animate-slide-down {
          animation: slideDown 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .no-scrollbar::-webkit-scrollbar {
          display: none;
        }
        .no-scrollbar {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>

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
                
                const isExpanded = expandedTicker === item.ticker;

                return (
                  <React.Fragment key={item.ticker}>
                    {/* 메인 데이터 행 */}
                    <tr
                      onClick={() => setExpandedTicker(isExpanded ? null : item.ticker)}
                      className={cn(
                        "group hover:bg-white/[0.02] cursor-pointer transition-all border-b border-zinc-800/30 select-none",
                        isExpanded ? "bg-white/[0.03]" : (idx === 0 ? "bg-indigo-500/[0.02]" : "")
                      )}
                    >
                      {/* 순위 */}
                      <td className="py-4 px-5">
                        <span className="text-zinc-650 font-mono text-xs">{String(idx + 1).padStart(2, '0')}</span>
                      </td>

                      {/* 종목 정보 */}
                      <td className="py-4 px-2">
                        <div className="flex items-center gap-2">
                          <div className="flex flex-col">
                            <span className="text-white font-bold text-sm tracking-tight">{item.name}</span>
                            <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-wider">{item.ticker}</span>
                          </div>
                          {d.has_news && (
                            <span 
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedNewsItem(item);
                              }}
                              className={cn(
                                "flex h-4.5 items-center px-1.5 rounded text-[8.5px] font-bold border animate-pulse cursor-pointer hover:scale-105 active:scale-95 transition-all select-none",
                                item.news_sentiment === "POSITIVE" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_6px_rgba(16,185,129,0.15)]" :
                                item.news_sentiment === "NEGATIVE" ? "bg-rose-500/10 text-rose-400 border-rose-500/20 shadow-[0_0_6px_rgba(244,63,94,0.15)]" :
                                "bg-amber-500/10 text-amber-500 border-amber-500/20 shadow-[0_0_6px_rgba(245,158,11,0.15)]"
                              )}
                            >
                              {item.news_sentiment === "POSITIVE" ? "AI 호재 🔥" :
                               item.news_sentiment === "NEGATIVE" ? "AI 악재 📉" : "뉴스 📰"}
                            </span>
                          )}
                          {/* 패턴 탑재 여부 칩 추가 */}
                          {item.patterns && item.patterns.length > 0 && (
                            <span className="flex h-4.5 items-center px-1 rounded bg-indigo-500/10 text-indigo-400 text-[8px] font-black border border-indigo-500/20">
                              {item.patterns.join(" / ")}
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
                            <span className="text-[10px] text-zinc-400 font-mono font-bold flex items-center gap-1">
                              {item.signal_score}
                              <ChevronDown size={11} className={cn("text-zinc-650 transition-transform duration-300", isExpanded && "rotate-180 text-indigo-400")} />
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* 액션 */}
                      <td className="py-4 px-5 text-right" onClick={(e) => e.stopPropagation()}>
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

                    {/* 아코디언 아웃 라인 3, 4번 동시 구현 */}
                    {isExpanded && (
                      <tr className="bg-zinc-950/70 border-b border-zinc-800/80">
                        <td colSpan={8} className="p-0">
                          <div className="overflow-hidden bg-zinc-950/40 p-6 border-l-4 border-indigo-500 animate-slide-down">
                            <div className="max-w-3xl mx-auto bg-gradient-to-br from-zinc-900 to-zinc-950/80 border border-zinc-800/80 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_10px_30px_rgba(0,0,0,0.5)] rounded-2xl p-6 flex flex-col gap-5">
                              <div className="flex items-center justify-between border-b border-zinc-850 pb-3.5">
                                <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
                                  <Activity size={15} className="text-indigo-400 animate-pulse" />
                                  Technical Score Breakdown
                                </span>
                                <span className="text-[10px] font-mono text-zinc-500 tracking-wider">QUANT SCORECARD • {item.ticker}</span>
                              </div>
                              
                              {/* 스코어 게이지바 차오르는 애니메이션 */}
                              <div className="flex items-center gap-4 bg-zinc-950/60 p-5 rounded-xl border border-zinc-850 shadow-inner">
                                <div className="flex flex-col gap-2 flex-1">
                                  <div className="flex justify-between items-end">
                                    <span className="text-xs text-zinc-400 font-semibold tracking-wide">종합 추천 스코어</span>
                                    <span className="text-2xl font-black font-mono tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-white to-zinc-300">
                                      {item.signal_score}
                                      <span className="text-xs text-zinc-650 font-normal ml-1">/ 100</span>
                                    </span>
                                  </div>
                                  <div className="w-full h-3.5 bg-zinc-900 rounded-full overflow-hidden p-[2.5px] border border-zinc-850">
                                    <div 
                                      className={cn(
                                        "h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_12px_rgba(99,102,241,0.5)]",
                                        item.signal_score >= 80 ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-rose-500 shadow-[0_0_15px_rgba(244,63,94,0.4)]" :
                                        item.signal_score >= 60 ? "bg-gradient-to-r from-indigo-500 to-amber-500 shadow-[0_0_15px_rgba(245,158,11,0.3)]" :
                                        "bg-indigo-500 shadow-[0_0_15px_rgba(99,102,241,0.3)]"
                                      )}
                                      style={{ width: `${item.signal_score}%` }}
                                    />
                                  </div>
                                </div>
                              </div>

                              {/* 2열 격자 구조의 칩 리스트 */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 max-h-[170px] overflow-y-auto pr-1.5 no-scrollbar mt-1">
                                {item.score_card && item.score_card.length > 0 ? (
                                  item.score_card.map((card, cidx) => (
                                    <div 
                                      key={cidx}
                                      className={cn(
                                        "flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-bold tracking-tight border transition-all duration-300 hover:bg-white/[0.01]",
                                        card.passed 
                                          ? "bg-emerald-500/[0.03] text-emerald-400 border-emerald-500/15 shadow-[inset_0_1px_0_rgba(16,185,129,0.05)]" 
                                          : "bg-rose-500/[0.03] text-rose-455 border-rose-500/15 shadow-[inset_0_1px_0_rgba(244,63,94,0.05)]"
                                      )}
                                    >
                                      <div className="flex items-center gap-2">
                                        <span className={cn(
                                          "w-1.5 h-1.5 rounded-full animate-pulse",
                                          card.passed ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" : "bg-rose-450 shadow-[0_0_8px_rgba(248,113,113,0.8)]"
                                        )} />
                                        <span className="text-zinc-300">{card.factor}</span>
                                      </div>
                                      <span className={cn(
                                        "font-mono text-[10px] px-1.5 py-0.5 rounded-md font-extrabold",
                                        card.passed ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"
                                      )}>
                                        {card.score > 0 ? `+${card.score}` : card.score}
                                      </span>
                                    </div>
                                  ))
                                ) : (
                                  <span className="text-xs text-zinc-650 italic col-span-2 text-center py-4">세부 채점 내역이 제공되지 않는 종목입니다.</span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 푸터 정보 */}
      <div className="px-5 py-3 bg-white/[0.01] border-t border-zinc-800/50 flex justify-between items-center">
        <div className="flex items-center gap-4 text-[10px] text-zinc-650 font-medium">
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
          * Click any row to expand details, AI sentiments, and scorecards
        </div>
      </div>

      {/* AI Sentiment Modal Popup */}
      {selectedNewsItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop blur overlay */}
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300"
            onClick={() => setSelectedNewsItem(null)}
          />
          
          {/* Holographic News Glass Card */}
          <div className={cn(
            "relative w-full max-w-lg bg-zinc-900/95 border-2 rounded-2xl p-6 shadow-[0_25px_60px_-15px_rgba(0,0,0,0.8)] z-10 transition-all duration-300 scale-100",
            selectedNewsItem.news_sentiment === "POSITIVE" ? "border-emerald-500/35 shadow-[0_0_30px_rgba(16,185,129,0.15)]" :
            selectedNewsItem.news_sentiment === "NEGATIVE" ? "border-rose-500/35 shadow-[0_0_30px_rgba(244,63,94,0.15)]" :
            "border-zinc-800 shadow-[0_0_30px_rgba(255,255,255,0.05)]"
          )}>
            {/* Dynamic Colored Top-border line decor */}
            <div className={cn(
              "absolute top-0 left-6 right-6 h-[2px] bg-gradient-to-r",
              selectedNewsItem.news_sentiment === "POSITIVE" ? "from-emerald-500 via-teal-400 to-indigo-500" :
              selectedNewsItem.news_sentiment === "NEGATIVE" ? "from-rose-500 via-pink-400 to-purple-500" :
              "from-zinc-700 via-zinc-500 to-zinc-750"
            )} />

            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-850 pb-4 mb-4 mt-1">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
                  <MessageSquare size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-black text-white tracking-wide uppercase">AI Sentiment & Signals</h3>
                  <p className="text-[10px] text-zinc-500 font-mono tracking-wider">{selectedNewsItem.name} ({selectedNewsItem.ticker})</p>
                </div>
              </div>

              {/* 패턴 배지 */}
              <div className="flex gap-1">
                {selectedNewsItem.patterns && selectedNewsItem.patterns.includes("VCP") && (
                  <div className="flex items-center px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 text-[8.5px] font-bold border border-indigo-500/30">
                    <VCPSvgIcon />
                    VCP
                  </div>
                )}
                {selectedNewsItem.patterns && selectedNewsItem.patterns.includes("CUP_AND_HANDLE") && (
                  <div className="flex items-center px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 text-[8.5px] font-bold border border-amber-500/30">
                    <CupAndHandleSvgIcon />
                    CUP & HANDLE
                  </div>
                )}
              </div>
            </div>

            {/* Sentiment spectrum */}
            <div className="flex flex-col gap-2.5 bg-zinc-950/60 p-4.5 rounded-xl border border-zinc-850/80 mb-4 shadow-inner">
              <div className="flex justify-between items-center text-[10px] text-zinc-500 font-extrabold tracking-wide">
                <span>BEARISH 📉</span>
                <span className="text-xs font-black text-white font-mono flex items-center gap-1.5">
                  뉴스 심리 온도
                  <span className={cn(
                    "px-1.5 py-0.5 rounded text-[10px] font-mono",
                    (selectedNewsItem.news_sentiment_score ?? 50) >= 60 ? "bg-emerald-500/10 text-emerald-400" :
                    (selectedNewsItem.news_sentiment_score ?? 50) <= 40 ? "bg-rose-500/10 text-rose-400" :
                    "bg-zinc-800 text-zinc-400"
                  )}>
                    {selectedNewsItem.news_sentiment_score ?? 50}%
                  </span>
                </span>
                <span>BULLISH 📈</span>
              </div>
              <div className="relative w-full h-1.5 bg-gradient-to-r from-rose-500/70 via-amber-400/70 to-emerald-500/70 rounded-full border border-zinc-900 shadow-inner">
                <div 
                  className="absolute w-3 h-3 -top-0.5 bg-white rounded-full border border-zinc-950 -translate-x-1/2 shadow-[0_0_12px_rgba(255,255,255,0.9)] animate-pulse transition-all duration-1000 ease-out"
                  style={{ left: `${selectedNewsItem.news_sentiment_score ?? 50}%` }}
                />
              </div>
            </div>

            {/* AI Summary card */}
            <div className="bg-gradient-to-b from-zinc-950/80 to-zinc-950/95 border border-zinc-850 p-5 rounded-xl shadow-[inset_0_1.5px_2px_rgba(0,0,0,0.8)] flex flex-col justify-between min-h-[120px] mb-5">
              <div>
                <div className="flex items-center justify-between gap-2 mb-3.5">
                  <span className={cn(
                    "text-[9px] font-black px-2 py-0.5 rounded border tracking-widest",
                    selectedNewsItem.news_sentiment === "POSITIVE" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                    selectedNewsItem.news_sentiment === "NEGATIVE" ? "bg-rose-500/10 text-rose-450 border-rose-500/20" :
                    "bg-zinc-500/10 text-zinc-400 border-zinc-850"
                  )}>
                    {selectedNewsItem.news_sentiment ?? "NEUTRAL"}
                  </span>
                  <span className="text-[9px] text-zinc-500 font-bold font-mono tracking-wider">AI REAL-TIME ANALYSIS</span>
                </div>
                
                <div className="relative pl-4 border-l-2 border-indigo-500/30">
                  <p className="text-xs text-zinc-300 font-semibold leading-relaxed tracking-wide">
                    {selectedNewsItem.news_summary ?? "이 종목에 관한 호재나 악재 뉴스를 스캔하고 분석하는 중입니다."}
                  </p>
                </div>
              </div>
              
              {selectedNewsItem.news_url && (
                <a 
                  href={selectedNewsItem.news_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="self-end flex items-center gap-1.5 mt-4 text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors font-black uppercase tracking-widest group/link"
                >
                  원문 기사 읽기
                  <ExternalLink size={11} className="group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 transition-transform" />
                </a>
              )}
            </div>

            {/* Footer Close Actions */}
            <div className="flex justify-end gap-2.5">
              <button
                onClick={() => setSelectedNewsItem(null)}
                className="px-4.5 py-2 bg-zinc-800 hover:bg-zinc-750 text-zinc-300 rounded-lg text-xs font-bold transition-all active:scale-95 border border-zinc-750/30"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

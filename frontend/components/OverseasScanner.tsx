"use client";

import React, { useState, useCallback } from "react";
import { 
  Radar, 
  RefreshCw, 
  TrendingUp, 
  TrendingDown,
  Newspaper,
  Plus, 
  Zap, 
  Eye, 
  Minus, 
  Info, 
  ExternalLink, 
  Activity, 
  MessageSquare,
  BarChart2,
  X
} from "lucide-react";
import { cn, reportHandledError } from "@/lib/utils";
import { scannerAPI } from "@/lib/api";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { toast } from "sonner";
import { useTimezone } from "@/store/timezoneStore";

interface ScoreCardFactor {
  factor: string;
  score: number;
  passed: boolean;
}

interface ScanResult {
  ticker: string;
  name: string;
  source?: string[];
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
  activeTab?: "15m" | "swing";
  setActiveTab?: (tab: "15m" | "swing") => void;
}

export function OverseasScanner({ 
  onAddToWatchlist, 
  watchlistTickers = [],
  activeTab = "15m",
  setActiveTab
}: OverseasScannerProps) {
  const [isManualScanning, setIsManualScanning] = useState(false);
  
  const { data: swrData, isLoading: swrLoading, mutate: mutateScan } = useSWR('/scanner/latest', fetcher, { 
    refreshInterval: 15000,
    onSuccess: () => setLastUpdated(new Date())
  });
  const results: ScanResult[] = Array.isArray(swrData) ? swrData : (swrData?.data || []);
  const isLoading = swrLoading || isManualScanning;

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isSpinning, setIsSpinning] = useState(false);
  const { selectedTimezone } = useTimezone();
  
  // 퀀트 스코어 팝업 모달 상태 관리
  const [selectedScoreItem, setSelectedScoreItem] = useState<ScanResult | null>(null);
  // AI 뉴스 상세 보기 모달 상태 관리
  const [selectedNewsItem, setSelectedNewsItem] = useState<ScanResult | null>(null);

  const runManualScan = useCallback(async () => {
    setIsManualScanning(true);
    setIsSpinning(true);
    try {
      await scannerAPI.runOverseasScan();
      toast.success("스캔이 백그라운드에서 시작되었습니다. 약 25초 뒤 자동으로 목록을 갱신합니다.");
      
      setTimeout(async () => {
        await mutateScan();
        setIsManualScanning(false);
        setIsSpinning(false);
        toast.success("스캔 갱신이 완료되었습니다.");
      }, 25000);
      
    } catch (error) {
      const msg = reportHandledError("Failed to run overseas scan", error);
      toast.error(`수동 스캔 실패: ${msg}`);
      setIsManualScanning(false);
      setIsSpinning(false);
    }
  }, [mutateScan]);

  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl shadow-xl flex flex-col h-full">
      {/* 아코디언 및 미세 스펙트럼 슬라이드 애니메이션 인라인 주입 */}
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-slide-down {
          animation: slideDown 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes newsTicker {
          0%   { transform: translateX(100%); }
          100% { transform: translateX(-100%); }
        }
        .animate-news-ticker {
          animation: newsTicker 18s linear infinite;
          white-space: nowrap;
          display: inline-block;
        }
        .animate-news-ticker:hover {
          animation-play-state: paused;
        }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        .custom-scrollbar::-webkit-scrollbar {
          height: 6px;
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.02);
          border-radius: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.12);
          border-radius: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.22);
        }
      `}</style>

      {/* 헤더 */}
      <div className="flex items-center justify-between p-5 border-b border-zinc-800/80">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
            <Radar size={22} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-tight">실시간 정밀 스캔</h2>
            <p className="text-zinc-500 text-xs font-medium">실시간 전수 조사 (Gap, News, RVOL, RS)</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-[10px] text-zinc-500 font-mono flex items-center gap-1.5 select-none">
              <span className="bg-zinc-800/80 text-zinc-400 px-1.5 py-0.5 rounded font-black tracking-widest">{selectedTimezone.abbr}</span>
              Last update: {lastUpdated.toLocaleTimeString('ko-KR', {
                timeZone: selectedTimezone.timeZone,
              })}
            </span>
          )}
          <button
            onClick={() => runManualScan()}
            disabled={isLoading || isManualScanning}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-medium transition-all active:scale-95 disabled:opacity-50"
            title="현재 캐시와 별개로 해외 마켓 스캔을 새로 실행합니다"
          >
            <RefreshCw size={13} className={cn((isSpinning || isManualScanning) && "animate-spin text-indigo-400")} />
            {isManualScanning ? "수동 스캔 중..." : isLoading ? "캐시 확인 중..." : "수동 스캔"}
          </button>
        </div>
      </div>

      {/* 2-Tab Selector inside Scanner Container */}
      <div className="flex border-b border-zinc-800/80 bg-zinc-900/20 px-5 pt-3 gap-6">
        <button
          onClick={() => setActiveTab?.("15m")}
          className={cn(
            "pb-3 text-xs font-bold transition-all duration-300 flex items-center gap-2 cursor-pointer border-b-2",
            activeTab === "15m"
              ? "border-amber-500 text-amber-400 font-extrabold"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          )}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full bg-amber-500", activeTab === "15m" && "animate-pulse")} />
          15m 단타(기존)
        </button>
        <button
          onClick={() => setActiveTab?.("swing")}
          className={cn(
            "pb-3 text-xs font-bold transition-all duration-300 flex items-center gap-2 cursor-pointer border-b-2",
            activeTab === "swing"
              ? "border-indigo-500 text-indigo-400 font-extrabold"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          )}
        >
          <span className={cn("w-1.5 h-1.5 rounded-full bg-indigo-500", activeTab === "swing" && "animate-pulse")} />
          내일 세력돌파 예측(스윙)
        </button>
      </div>

      {/* 테이블 영역 */}
      <div className="flex-1 overflow-auto custom-scrollbar">
        {isLoading && results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            <Radar size={40} className="animate-ping mb-4 opacity-20 text-indigo-500" />
            <p className="text-sm font-medium">
              {isManualScanning ? "해외 마켓 수동 스캔을 실행 중입니다..." : "최신 스캐너 캐시를 확인하고 있습니다..."}
            </p>
            <p className="text-xs text-zinc-600 mt-2">
              {isManualScanning ? "Stage 1: 15분봉 벌크 스캔 중 (7,000+ Tickers)" : "저장된 최신 시그널을 불러오는 중"}
            </p>
          </div>
        ) : results.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
            <Zap size={30} className="mb-3 opacity-20" />
            <p className="text-sm">자동 캐시에 저장된 최신 시그널이 없습니다.</p>
            <p className="text-xs text-zinc-600 mt-2">정규장 외에는 자동 캐시가 비어 있을 수 있습니다. 필요하면 수동 스캔을 실행하세요.</p>
          </div>
        ) : (
          <table className="w-full min-w-[850px] text-left border-collapse">
            <thead>
              <tr className="border-b border-zinc-800/50 text-zinc-500 text-[10px] uppercase tracking-[0.1em]">
                <th className="py-4 px-5 font-semibold">Rank</th>
                <th className="py-4 px-2 font-semibold">Ticker / Name</th>
                <th className="py-4 px-4 font-semibold text-right">Price</th>
                <th className="py-4 px-4 font-semibold text-center">
                  <HeaderTooltip title="Open Gap / RVOL" desc="Open Gap: 직전 거래일 마지막 15분봉 종가 대비 당일 첫 15분봉 시가의 갭 비율. RVOL: 최근 20개 마감 15분봉 평균 대비 마지막 마감 15분봉 거래량 비율." />
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
              {results.filter((r) => !r.source || r.source.length === 0 || r.source.some((s) => s !== "WATCHLIST")).map((item, idx) => {
                const signal = SIGNAL_CONFIG[item.signal_type] || SIGNAL_CONFIG.NEUTRAL;
                const SignalIcon = signal.icon;
                const isInWatchlist = watchlistTickers.includes(item.ticker);
                const d = item.details;

                return (
                  <React.Fragment key={item.ticker}>
                    {/* 메인 데이터 행 */}
                    <tr
                      onClick={() => setSelectedScoreItem(item)}
                      className={cn(
                        "group hover:bg-white/[0.02] cursor-pointer transition-all border-b border-zinc-800/30 select-none",
                        idx === 0 ? "bg-indigo-500/[0.02]" : ""
                      )}
                    >
                      {/* 순위 */}
                      <td className="py-4 px-5">
                        <span className="text-zinc-650 font-mono text-xs">{String(idx + 1).padStart(2, '0')}</span>
                      </td>

                      {/* 종목 정보 — 수직 스택 */}
                      <td className="py-3 px-2 max-w-[160px]">
                        <div className="flex flex-col gap-0.5">
                          {/* 회사명 */}
                          <span className="text-white font-bold text-sm tracking-tight leading-tight line-clamp-1">
                            {item.name}
                          </span>

                          {/* 티커 + 패턴 뱃지 한 줄 */}
                          <div className="flex items-center gap-1.5">
                            <span className="text-zinc-500 font-mono text-[10px] uppercase tracking-wider">
                              {item.ticker}
                            </span>
                            {item.patterns && item.patterns.length > 0 && (
                              <span className={cn(
                                "inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[8px] font-black border tracking-wide",
                                item.patterns.includes("VCP")
                                  ? "bg-indigo-500/10 text-indigo-300 border-indigo-500/20"
                                  : "bg-amber-500/10 text-amber-300 border-amber-500/20"
                              )}>
                                <Zap size={7} className="shrink-0" />
                                {item.patterns.join("·")}
                              </span>
                            )}
                          </div>

                          {/* 뉴스 흘러가는 줄 — 뉴스 있을 때만 */}
                          {d.has_news && item.news_summary && (() => {
                            const isPositive = item.news_sentiment === "POSITIVE";
                            const isNegative = item.news_sentiment === "NEGATIVE";
                            return (
                              <button
                                onClick={(e) => { e.stopPropagation(); setSelectedNewsItem(item); }}
                                className="mt-0.5 overflow-hidden w-full cursor-pointer"
                                title="클릭해서 AI 뉴스 분석 보기"
                              >
                                <div className={cn(
                                  "flex items-center gap-1 text-[9px] font-bold",
                                  isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-sky-400"
                                )}>
                                  {/* 감성 아이콘 */}
                                  {isPositive ? (
                                    <TrendingUp size={8} className="shrink-0" />
                                  ) : isNegative ? (
                                    <TrendingDown size={8} className="shrink-0" />
                                  ) : (
                                    <Newspaper size={8} className="shrink-0" />
                                  )}
                                  {/* 흘러가는 텍스트 */}
                                  <span className="overflow-hidden flex-1">
                                    <span className="animate-news-ticker opacity-80 hover:opacity-100">
                                      {item.news_summary}
                                    </span>
                                  </span>
                                </div>
                              </button>
                            );
                          })()}
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
                              <BarChart2 size={11} className="text-zinc-600 group-hover:text-indigo-400 transition-colors" />
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
        <div className="text-[10px] text-zinc-500 italic flex items-center gap-1">
          <BarChart2 size={10} className="text-zinc-600" />
          행 클릭: 스코어 상세 &nbsp;·&nbsp; AI 칩 클릭: 뉴스 분석
        </div>
      </div>

      {/* ── 퀀트 스코어 팝업 모달 ── */}
      {selectedScoreItem && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/65 backdrop-blur-sm"
            onClick={() => setSelectedScoreItem(null)}
          />
          <div className={cn(
            "relative w-full max-w-xl bg-zinc-900/97 border-2 rounded-2xl shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] z-10 overflow-hidden",
            selectedScoreItem.signal_score >= 80
              ? "border-indigo-500/40 shadow-[0_0_40px_rgba(99,102,241,0.15)]"
              : selectedScoreItem.signal_score >= 60
              ? "border-amber-500/30 shadow-[0_0_40px_rgba(245,158,11,0.10)]"
              : "border-zinc-700"
          )}>
            {/* 상단 컬러 라인 */}
            <div className={cn(
              "absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r",
              selectedScoreItem.signal_score >= 80
                ? "from-indigo-500 via-purple-500 to-rose-500"
                : selectedScoreItem.signal_score >= 60
                ? "from-indigo-500 to-amber-500"
                : "from-zinc-600 to-zinc-700"
            )} />

            {/* 헤더 */}
            <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-zinc-800">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
                  <Activity size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-black text-white tracking-wide uppercase">Technical Score Breakdown</h3>
                  <p className="text-[10px] text-zinc-500 font-mono tracking-wider mt-0.5">
                    QUANT SCORECARD · {selectedScoreItem.name} ({selectedScoreItem.ticker})
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedScoreItem(null)}
                className="w-8 h-8 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 hover:text-white transition-all active:scale-90"
              >
                <X size={15} />
              </button>
            </div>

            <div className="p-6 flex flex-col gap-5">
              {/* 스코어 게이지바 */}
              <div className="bg-zinc-950/60 p-5 rounded-xl border border-zinc-800 shadow-inner">
                <div className="flex justify-between items-end mb-3">
                  <span className="text-xs text-zinc-400 font-semibold tracking-wide">종합 추천 스코어</span>
                  <span className="text-3xl font-black font-mono tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-white to-zinc-400">
                    {selectedScoreItem.signal_score}
                    <span className="text-sm text-zinc-600 font-normal ml-1">/ 100</span>
                  </span>
                </div>
                <div className="w-full h-4 bg-zinc-900 rounded-full overflow-hidden p-[2.5px] border border-zinc-850">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-1000 ease-out",
                      selectedScoreItem.signal_score >= 80
                        ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-rose-500 shadow-[0_0_16px_rgba(244,63,94,0.5)]"
                        : selectedScoreItem.signal_score >= 60
                        ? "bg-gradient-to-r from-indigo-500 to-amber-500 shadow-[0_0_16px_rgba(245,158,11,0.4)]"
                        : "bg-indigo-500 shadow-[0_0_16px_rgba(99,102,241,0.4)]"
                    )}
                    style={{ width: `${selectedScoreItem.signal_score}%` }}
                  />
                </div>
                {/* 점수 구간 레이블 */}
                <div className="flex justify-between mt-2 text-[9px] text-zinc-700 font-mono">
                  <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                </div>
              </div>

              {/* 팩터 칩 2열 그리드 */}
              <div className="grid grid-cols-2 gap-2">
                {selectedScoreItem.score_card && selectedScoreItem.score_card.length > 0 ? (
                  selectedScoreItem.score_card.map((card, cidx) => (
                    <div
                      key={cidx}
                      className={cn(
                        "flex items-center justify-between px-3 py-2.5 rounded-xl text-xs border transition-all",
                        card.passed
                          ? "bg-emerald-500/[0.05] border-emerald-500/20 shadow-[inset_0_1px_0_rgba(16,185,129,0.07)]"
                          : "bg-rose-500/[0.05] border-rose-500/20 shadow-[inset_0_1px_0_rgba(244,63,94,0.07)]"
                      )}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={cn(
                          "w-1.5 h-1.5 shrink-0 rounded-full",
                          card.passed
                            ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.9)]"
                            : "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.9)]"
                        )} />
                        <span className={cn("font-medium truncate", card.passed ? "text-zinc-300" : "text-zinc-500")}>
                          {card.factor}
                        </span>
                      </div>
                      <span className={cn(
                        "font-mono text-[10px] px-1.5 py-0.5 rounded font-extrabold shrink-0 ml-2",
                        card.passed ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/10 text-rose-500"
                      )}>
                        {card.score > 0 ? `+${card.score}` : card.score}
                      </span>
                    </div>
                  ))
                ) : (
                  <span className="col-span-2 text-xs text-zinc-600 italic text-center py-6">
                    세부 채점 내역이 제공되지 않는 종목입니다.
                  </span>
                )}
              </div>

              {/* 합계 요약 */}
              {selectedScoreItem.score_card && selectedScoreItem.score_card.length > 0 && (
                <div className="flex items-center justify-between px-4 py-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
                  <span className="text-[11px] text-zinc-500 font-semibold">
                    통과 {selectedScoreItem.score_card.filter(c => c.passed).length} / 전체 {selectedScoreItem.score_card.length} 항목
                  </span>
                  <span className="text-[11px] font-black font-mono text-indigo-400">
                    합산 +{selectedScoreItem.score_card.filter(c => c.passed).reduce((s, c) => s + c.score, 0)}pt
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

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

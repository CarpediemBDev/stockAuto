'use client';

import React, { useState, useCallback } from 'react';
import { Compass, ShieldCheck, Flame, Layers, TrendingUp, TrendingDown, HelpCircle, Activity, RefreshCw } from 'lucide-react';

import { scannerAPI } from '@/lib/api';
import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { useTimezone } from '@/store/timezoneStore';
import { toast } from 'sonner';
import { cn, reportHandledError } from '@/lib/utils';

interface SwingPredictorCardProps {
  activeTab?: "15m" | "swing";
  setActiveTab?: (tab: "15m" | "swing") => void;
}

interface SwingCandidate {
  ticker: string;
  score: number;
  vcp_triggered: boolean;
  vud_ratio: number;
  squeeze_pct: number;
  obv_divergence: number;
  close: number;
  change_pct: number;
  is_bullish_trend: boolean;
}

interface SwingPredictionResponse {
  candidates: SwingCandidate[];
  scope: "global";
  sync_status: "empty" | "failed" | "fresh" | "refreshing" | "stale";
  updated_at: string | null;
}

export function SwingPredictorCard({ activeTab = "swing", setActiveTab }: SwingPredictorCardProps) {
  const { data: swrData, isLoading: swrLoading, mutate: mutateSwing } = useSWR('/scanner/swing-predict', fetcher, { refreshInterval: 15000 });
  const payload: SwingPredictionResponse = swrData || { candidates: [], scope: "global", sync_status: "empty", updated_at: null };
  const candidates = payload.candidates;
  const syncStatus = payload.sync_status;
  const updatedAt = payload.updated_at;

  const [refreshing, setRefreshing] = useState(false);
  const { selectedTimezone } = useTimezone();
  const loading = swrLoading;

  const refreshSwingCandidates = useCallback(async () => {
    setRefreshing(true);
    try {
      await scannerAPI.refreshSwingPredict();
      toast.success("스윙 갱신이 백그라운드에서 시작되었습니다. 잠시 후 자동 갱신됩니다.");
      // API가 백그라운드 태스크 시작을 알리고 너무 빨리 종료되므로,
      // 유저가 클릭 피드백을 눈으로 볼 수 있도록 3초 후 데이터 리프레시
      setTimeout(async () => {
        await mutateSwing();
        setRefreshing(false);
      }, 3000);
    } catch (error) {
      const msg = reportHandledError('Failed to refresh swing predictions', error);
      toast.error(`스윙 예측 수동 갱신 실패: ${msg}`);
      setRefreshing(false);
    }
  }, [mutateSwing]);

  if (loading) {
    return (
      <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-zinc-900 rounded-2xl animate-pulse"></div>
            <div className="space-y-2">
              <div className="w-32 h-5 bg-zinc-900 rounded-md animate-pulse"></div>
              <div className="w-48 h-3.5 bg-zinc-900 rounded-md animate-pulse"></div>
            </div>
          </div>
          <div className="w-24 h-7 bg-zinc-900 rounded-lg animate-pulse"></div>
        </div>
        {/* 2-Tab Selector inside Scanner Container */}
        <div className="flex border-b border-zinc-800/80 bg-zinc-900/20 px-2 pt-1 gap-6 mb-6">
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-44 bg-zinc-900/50 rounded-2xl border border-zinc-800 animate-pulse"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl">
      {/* 프리미엄 헤더 */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 pb-4 border-b border-zinc-900 gap-4">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <Compass size={22} className="text-indigo-400" />
          </div>
          <div>
            <h3 className="text-base font-black text-slate-200 tracking-tight flex items-center gap-2">
              내일 세력돌파 예측 스윙 스캐너
              <span className="text-[9px] bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-2 py-0.5 rounded font-black uppercase tracking-wider">
                Daily Swing
              </span>
            </h3>
            <p className="text-xs text-zinc-400 font-medium">공용 시장 주도주 풀의 120일 일봉을 분석하여 변동성 및 수급 수축 한계점에 도달한 종목을 포착합니다.</p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-end md:self-auto">
          <span className="text-[10px] bg-zinc-900 text-zinc-400 border border-zinc-800 font-mono px-3 py-1 rounded-full flex items-center gap-1.5 select-none">
            <span className={cn(
              "w-1.5 h-1.5 rounded-full animate-pulse",
              syncStatus === "fresh" ? "bg-emerald-500" :
              syncStatus === "stale" ? "bg-amber-500" :
              syncStatus === "failed" ? "bg-rose-500" :
              "bg-indigo-500"
            )}></span>
            GLOBAL MARKET · {syncStatus.toUpperCase()} SWING SIGNALS
          </span>
          {updatedAt && (
            <span className="text-[10px] text-zinc-400 font-mono flex items-center gap-1.5">
              <span className="bg-zinc-800/80 text-zinc-400 px-1.5 py-0.5 rounded font-black tracking-widest">{selectedTimezone.abbr}</span>
              {new Date(updatedAt).toLocaleTimeString('ko-KR', {
                timeZone: selectedTimezone.timeZone,
              })}
            </span>
          )}
          <button
            onClick={() => refreshSwingCandidates()}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50 border border-zinc-800"
            title="모든 사용자가 공유하는 공용 시장 주도주 풀의 스윙 예측을 새로 계산합니다"
          >
            <RefreshCw size={13} className={cn(refreshing && "animate-spin text-indigo-400")} />
            {refreshing ? "갱신 중..." : "수동 갱신"}
          </button>
        </div>
      </div>

      {/* 2-Tab Selector inside Scanner Container */}
      <div className="flex border-b border-zinc-800/80 bg-zinc-900/20 px-2 pt-1 gap-6 mb-6">
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

      {/* 포착된 종목 리스트 */}
      {candidates.length === 0 ? (
        <div className="py-16 text-center bg-zinc-900/20 rounded-2xl border border-dashed border-zinc-800">
          <HelpCircle size={40} className="mx-auto text-zinc-600 mb-3" />
          <p className="text-sm font-bold text-zinc-500">저장된 스윙 예측 후보가 없습니다.</p>
          <p className="text-xs text-zinc-600 mt-1">
            {syncStatus === "refreshing"
              ? "현재 스윙 후보를 분석하는 중입니다."
              : syncStatus === "failed"
                ? "최근 스윙 예측 갱신에 실패했습니다. 잠시 후 수동 갱신을 다시 실행해 주세요."
                : "수동 갱신을 실행하면 공용 시장 주도주 풀을 새로 분석합니다."}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {candidates.map((c) => {
            // 점수에 따른 테마 색상 결정
            const isHighProb = c.score >= 80;
            const isMidProb = c.score >= 50 && c.score < 80;
            
            return (

              <div 
                key={c.ticker} 
                className="bg-zinc-900/40 hover:bg-zinc-900/80 border border-zinc-800/80 hover:border-indigo-500/30 rounded-2xl p-5 transition-all duration-300 relative overflow-hidden group"
              >
                {/* 점수에 따른 우측 상단 글로우 효과 */}
                {isHighProb && (
                  <div className="absolute -top-10 -right-10 w-24 h-24 bg-indigo-500/10 rounded-full blur-2xl group-hover:bg-indigo-500/20 transition-colors duration-300"></div>
                )}

                <div className="flex justify-between items-start mb-4 relative z-10">
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-black text-slate-100 group-hover:text-indigo-400 transition-colors duration-300">{c.ticker}</span>
                      {c.is_bullish_trend ? (
                        <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-black select-none">
                          정배열 추세
                        </span>
                      ) : (
                        <span className="text-[9px] bg-zinc-800 text-zinc-500 border border-zinc-700/50 px-1.5 py-0.5 rounded font-black select-none">
                          보합/횡보
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-zinc-500 font-bold mt-0.5">${c.close.toFixed(2)}</span>
                  </div>

                  <div className="flex flex-col items-end">
                    {c.change_pct >= 0 ? (
                      <span className="text-xs font-bold text-rose-500 flex items-center gap-0.5">
                        <TrendingUp size={14} />
                        +{c.change_pct}%
                      </span>
                    ) : (
                      <span className="text-xs font-bold text-emerald-400 flex items-center gap-0.5">
                        <TrendingDown size={14} />
                        {c.change_pct}%
                      </span>
                    )}
                  </div>
                </div>

                {/* 내일 돌파 예측 확률 스코어 바 */}
                <div className="mb-4">
                  <div className="flex justify-between items-center text-xs mb-1.5 font-bold">
                    <span className="text-zinc-400">내일 세력돌파 예상 점수</span>
                    <span className={`
                      ${isHighProb ? 'text-indigo-400 font-black' : isMidProb ? 'text-emerald-400 font-black' : 'text-zinc-500'}
                    `}>
                      {c.score} / 100
                    </span>
                  </div>
                  <div className="w-full h-2.5 bg-zinc-950 rounded-full overflow-hidden p-0.5 border border-zinc-800">
                    <div 
                      className={`h-full rounded-full transition-all duration-1000 bg-gradient-to-r
                        ${isHighProb 
                          ? 'from-indigo-500 via-purple-500 to-pink-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]' 
                          : isMidProb 
                          ? 'from-emerald-500 to-teal-500' 
                          : 'from-zinc-600 to-zinc-500'
                        }
                      `}
                      style={{ width: `${c.score}%` }}
                    ></div>
                  </div>
                </div>

                {/* 퀀트 다중 진단 조건 배지들 */}
                <div className="flex flex-wrap gap-2 pt-2 border-t border-zinc-900 text-[10px] font-black">
                  {/* VCP 수축 배지 */}
                  {c.vcp_triggered ? (
                    <span className="bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-1 rounded-lg flex items-center gap-1">
                      <ShieldCheck size={11} />
                      VCP 수렴 완료
                    </span>
                  ) : c.squeeze_pct < 30.0 ? (
                    <span className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 px-2 py-1 rounded-lg flex items-center gap-1">
                      <Layers size={11} />
                      VCP 진폭 압축 중
                    </span>
                  ) : null}

                  {/* Volume Dry-up 배지 */}
                  {c.vud_ratio <= 0.40 ? (
                    <span className="bg-rose-500/10 text-rose-400 border border-rose-500/30 px-2 py-1 rounded-lg flex items-center gap-1">
                      <Activity size={11} className="animate-pulse" />
                      VUD 극감 (매도 씨 마름)
                    </span>
                  ) : c.vud_ratio <= 0.70 ? (
                    <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-1 rounded-lg">
                      VUD 건조 ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  ) : (
                    <span className="bg-zinc-800/80 text-zinc-500 border border-zinc-800 px-2 py-1 rounded-lg">
                      거래량 보합 ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  )}

                  {/* OBV 세력 매집 다이버전스 배지 */}
                  {c.obv_divergence > 10.0 ? (
                    <span className="bg-rose-500/10 text-rose-400 border border-rose-500/30 px-2 py-1 rounded-lg flex items-center gap-1">
                      <Flame size={11} />
                      OBV 세력 매집중 ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : c.obv_divergence > 1.0 ? (
                    <span className="bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-1 rounded-lg">
                      OBV 매집 포착 ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : null}

                  {/* BB 스퀴즈 압착 강도 배지 */}
                  {c.squeeze_pct <= 20.0 ? (
                    <span className="bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 px-2 py-1 rounded-lg">
                      🧭 BB 대압착 (에너지 100% 장착)
                    </span>
                  ) : c.squeeze_pct <= 40.0 ? (
                    <span className="bg-purple-500/10 text-purple-400 border border-purple-500/30 px-2 py-1 rounded-lg">
                      🧭 BB 수축 (에너지 충전중)
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

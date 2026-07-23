'use client';

import React, { useState, useCallback, useEffect } from 'react';
import { Compass, ShieldCheck, Flame, Layers, TrendingUp, TrendingDown, HelpCircle, Activity, RefreshCw } from 'lucide-react';

import { scannerAPI, translationAPI } from '@/lib/api';
import useSWR from 'swr';
import { pollInterval } from '@/lib/sse';
import { fetcher } from '@/lib/api';
import { useTimezone } from '@/store/timezoneStore';
import { toast } from 'sonner';
import { cn, reportHandledError, getScoreColor, getScoreBarColor } from '@/lib/utils';
import { ScannerTabs, type ScannerTab } from '@/components/ScannerTabs';
import { useTranslations } from "next-intl";

interface SwingPredictorCardProps {
  activeTab?: ScannerTab;
  setActiveTab?: (tab: ScannerTab) => void;
}

interface SwingCandidate {
  ticker: string;
  score: number;
  vcp_triggered: boolean;
  vud_ratio: number;
  bollinger_band_width_percentile: number;
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
  const t = useTranslations("scanner");
  const { data: swrData, isLoading: swrLoading, mutate: mutateSwing } = useSWR('/scanner/swing-predict', fetcher, { refreshInterval: pollInterval(15000) });
  const payload: SwingPredictionResponse = swrData || { candidates: [], scope: "global", sync_status: "empty", updated_at: null };
  const candidates = payload.candidates;
  const syncStatus = payload.sync_status;
  const updatedAt = payload.updated_at;

  const [refreshing, setRefreshing] = useState(false);
  const [translations, setTranslations] = useState<Record<string, string>>({});

  useEffect(() => {
    translationAPI.getAll().then(res => {
      const map: Record<string, string> = {};
      res.data.forEach((t: { ticker: string; name_ko: string }) => {
        map[t.ticker.toUpperCase()] = t.name_ko;
      });
      setTranslations(map);
    }).catch(err => {
      console.warn("Failed to load translations", err);
    });
  }, []);
  const { selectedTimezone } = useTimezone();
  const loading = swrLoading;

  const refreshSwingCandidates = useCallback(async () => {
    setRefreshing(true);
    try {
      await scannerAPI.refreshSwingPredict();
      toast.success(t("swing.toast_started"));
      // API가 백그라운드 태스크 시작을 알리고 너무 빨리 종료되므로,
      // 유저가 클릭 피드백을 눈으로 볼 수 있도록 3초 후 데이터 리프레시
      setTimeout(async () => {
        await mutateSwing();
        setRefreshing(false);
      }, 3000);
    } catch (error) {
      const msg = reportHandledError('Failed to refresh swing predictions', error);
      toast.error(t("swing.toast_failed", { msg }));
      setRefreshing(false);
    }
  }, [mutateSwing, t]);

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
        <ScannerTabs activeTab={activeTab} setActiveTab={setActiveTab} className="px-2 pt-1 mb-6" />
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
            <h3 className="text-base font-black text-zinc-200 tracking-tight flex items-center gap-2">
              {t("swing.title")}
              <span className="text-[11px] bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-2 py-0.5 rounded font-black uppercase tracking-wider">
                Daily Swing
              </span>
            </h3>
            <p className="text-xs text-zinc-400 font-medium">{t("swing.subtitle")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 self-end md:self-auto">
          <span className="text-[11px] bg-zinc-900 text-zinc-400 border border-zinc-800 font-mono px-3 py-1 rounded-full hidden sm:flex items-center gap-1.5 select-none whitespace-nowrap">
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
            <span className="text-[11px] text-zinc-400 font-mono flex items-center gap-1.5">
              <span className="bg-zinc-800/80 text-zinc-400 px-1.5 py-0.5 rounded font-black tracking-widest">{selectedTimezone.abbr}</span>
              {new Date(updatedAt).toLocaleTimeString('ko-KR', {
                timeZone: selectedTimezone.timeZone,
              })}
            </span>
          )}
          <button
            onClick={() => refreshSwingCandidates()}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 text-zinc-300 rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50 border border-zinc-800 whitespace-nowrap"
            title={t("swing.refresh_title")}
          >
            <RefreshCw size={13} className={cn(refreshing && "animate-spin text-indigo-400")} />
            {refreshing ? t("swing.refreshing") : t("swing.refresh")}
          </button>
        </div>
      </div>

      <ScannerTabs activeTab={activeTab} setActiveTab={setActiveTab} className="px-2 pt-1 mb-6" />

      {/* 포착된 종목 리스트 */}
      {candidates.length === 0 ? (
        <div className="py-16 text-center bg-zinc-900/20 rounded-2xl border border-dashed border-zinc-800">
          <HelpCircle size={40} className="mx-auto text-zinc-600 mb-3" />
          <p className="text-sm font-bold text-zinc-500">{t("swing.empty_title")}</p>
          <p className="text-xs text-zinc-600 mt-1">
            {syncStatus === "refreshing"
              ? t("swing.empty_analyzing")
              : syncStatus === "failed"
                ? t("swing.empty_failed")
                : t("swing.empty_hint")}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {candidates.map((c, index) => {
            // 점수에 따른 테마 색상 결정
            const isHighProb = c.score >= 80;
            
            
            return (

              <div 
                key={c.ticker} 
                className={cn("bg-zinc-900/40 hover:bg-zinc-900/80 border rounded-2xl p-5 transition-all duration-300 relative overflow-hidden group", index === 0 ? "border-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.15)]" : "border-zinc-800/80 hover:border-indigo-500/30")}>
                {/* 1위 강조 뱃지 */}
                {index === 0 && (
                  <div className="absolute top-0 right-0 bg-amber-500/20 text-amber-400 text-[11px] font-black px-2 py-1 rounded-bl-xl border-l border-b border-amber-500/30 flex items-center gap-1">
                    👑 RANK 1
                  </div>
                )}
                {/* 점수에 따른 우측 상단 글로우 효과 */}
                {isHighProb && (
                  <div className="absolute -top-10 -right-10 w-24 h-24 bg-indigo-500/10 rounded-full blur-2xl group-hover:bg-indigo-500/20 transition-colors duration-300"></div>
                )}

                <div className="flex justify-between items-start mb-4 relative z-10">
                  <div className="flex flex-col">
                    <div className="flex items-baseline gap-2">
                      <span className="text-lg font-black text-zinc-100 group-hover:text-indigo-400 transition-colors duration-300">{c.ticker}</span>
                      {translations[c.ticker.toUpperCase()] && (
                        <span className="text-xs font-bold text-zinc-400 truncate max-w-[120px]" title={translations[c.ticker.toUpperCase()]}>
                          {translations[c.ticker.toUpperCase()]}
                        </span>
                      )}
                      {c.is_bullish_trend ? (
                        <span className="text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded font-black select-none whitespace-nowrap">
                          {t("swing.uptrend")}
                        </span>
                      ) : (
                        <span className="text-[11px] bg-zinc-800 text-zinc-500 border border-zinc-700/50 px-1.5 py-0.5 rounded font-black select-none whitespace-nowrap">
                          {t("swing.sideways")}
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-zinc-500 font-bold mt-0.5">${c.close.toFixed(2)}</span>
                  </div>

                  <div className="flex flex-col items-end">
                    {c.change_pct >= 0 ? (
                      <span className="text-xs font-bold text-emerald-400 flex items-center gap-0.5">
                        <TrendingUp size={14} />
                        +{c.change_pct}%
                      </span>
                    ) : (
                      <span className="text-xs font-bold text-rose-400 flex items-center gap-0.5">
                        <TrendingDown size={14} />
                        {c.change_pct}%
                      </span>
                    )}
                  </div>
                </div>

                {/* 내일 돌파 예측 확률 스코어 바 */}
                <div className="mb-4">
                  <div className="flex justify-between items-center text-xs mb-1.5 font-bold">
                    <span className="text-zinc-400">{t("swing.score_label")}</span>
                    <span className={getScoreColor(c.score).split(' ')[0] + ' font-black'}>
                      {c.score} / 100
                    </span>
                  </div>
                  <div className="w-full h-2.5 bg-zinc-950 rounded-full overflow-hidden p-0.5 border border-zinc-800">
                    <div className={`h-full rounded-full transition-all duration-1000 ${getScoreBarColor(c.score)}`}
                      style={{ width: `${c.score}%` }}
                    ></div>
                  </div>
                </div>

                {/* 퀀트 다중 진단 조건 배지들 */}
                <div className="flex flex-wrap gap-2 pt-2 border-t border-zinc-900 text-[11px] font-bold">
                  {/* VCP 수축 배지 */}
                  {c.vcp_triggered ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title={t("swing.vcp_done_tip")}>
                      <ShieldCheck size={11} className="text-amber-400" />
                      {t("swing.vcp_done")}
                    </span>
                  ) : c.bollinger_band_width_percentile < 30.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title={t("swing.vcp_compress_tip")}>
                      <Layers size={11} className="text-indigo-400" />
                      {t("swing.vcp_compress")}
                    </span>
                  ) : null}

                  {/* Volume Dry-up 배지 */}
                  {c.vud_ratio <= 0.40 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title={t("swing.vud_extreme_tip")}>
                      <Activity size={11} className="animate-pulse text-emerald-400" />
                      {t("swing.vud_extreme")}
                    </span>
                  ) : c.vud_ratio <= 0.70 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help" title={t("swing.vud_dry_tip")}>
                      {t("swing.vud_dry")} ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  ) : (
                    <span className="bg-zinc-900 text-zinc-500 border border-zinc-800 px-2 py-1 rounded-lg cursor-help" title={t("swing.vud_normal_tip")}>
                      {t("swing.vud_normal")} ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  )}

                  {/* OBV 세력 매집 다이버전스 배지 */}
                  {c.obv_divergence > 10.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title={t("swing.obv_strong_tip")}>
                      <Flame size={11} className="text-amber-400" />
                      {t("swing.obv_strong")} ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : c.obv_divergence > 1.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help" title={t("swing.obv_weak_tip")}>
                      {t("swing.obv_weak")} ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : null}

                  {/* BB 스퀴즈 압착 강도 배지 */}
                  {c.bollinger_band_width_percentile <= 20.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg cursor-help flex items-center gap-1" title={t("swing.bb_squeeze_tip")}><span className="text-indigo-400">🧭</span>
                      {t("swing.bb_squeeze")}
                    </span>
                  ) : c.bollinger_band_width_percentile <= 40.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help flex items-center gap-1" title={t("swing.bb_contract_tip")}><span className="text-purple-400">🧭</span>
                      {t("swing.bb_contract")}
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

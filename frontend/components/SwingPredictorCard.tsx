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
              내일 세력돌파 예측 스윙 스캐너
              <span className="text-[11px] bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 px-2 py-0.5 rounded font-black uppercase tracking-wider">
                Daily Swing
              </span>
            </h3>
            <p className="text-xs text-zinc-400 font-medium">공용 시장 주도주 풀의 120일 일봉을 분석하여 변동성 및 수급 수축 한계점에 도달한 종목을 포착합니다.</p>
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
            title="모든 사용자가 공유하는 공용 시장 주도주 풀의 스윙 예측을 새로 계산합니다"
          >
            <RefreshCw size={13} className={cn(refreshing && "animate-spin text-indigo-400")} />
            {refreshing ? "갱신 중..." : "수동 갱신"}
          </button>
        </div>
      </div>

      <ScannerTabs activeTab={activeTab} setActiveTab={setActiveTab} className="px-2 pt-1 mb-6" />

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
                          정배열 추세
                        </span>
                      ) : (
                        <span className="text-[11px] bg-zinc-800 text-zinc-500 border border-zinc-700/50 px-1.5 py-0.5 rounded font-black select-none whitespace-nowrap">
                          보합/횡보
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
                    <span className="text-zinc-400">내일 세력돌파 예상 점수</span>
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
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title="주가 변동성이 극도로 축소되며 세력이 에너지를 응축하는 VCP 패턴 완료 (호재)">
                      <ShieldCheck size={11} className="text-amber-400" />
                      VCP 수렴 완료
                    </span>
                  ) : c.bollinger_band_width_percentile < 30.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title="VCP 패턴 진행 중으로 변동성이 줄어들고 있음">
                      <Layers size={11} className="text-indigo-400" />
                      VCP 진폭 압축 중
                    </span>
                  ) : null}

                  {/* Volume Dry-up 배지 */}
                  {c.vud_ratio <= 0.40 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title="거래량이 극단적으로 마르며 매도세가 소진되었음을 의미 (강력한 반등 신호)">
                      <Activity size={11} className="animate-pulse text-emerald-400" />
                      VUD 극감 (매도 씨 마름)
                    </span>
                  ) : c.vud_ratio <= 0.70 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help" title="최근 거래량이 줄어들며 조정 장세가 마무리되는 중">
                      VUD 건조 ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  ) : (
                    <span className="bg-zinc-900 text-zinc-500 border border-zinc-800 px-2 py-1 rounded-lg cursor-help" title="평소와 비슷한 거래량 유지 중">
                      거래량 보합 ({Math.round(c.vud_ratio * 100)}%)
                    </span>
                  )}

                  {/* OBV 세력 매집 다이버전스 배지 */}
                  {c.obv_divergence > 10.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg flex items-center gap-1 cursor-help" title="거래량이 극단적으로 마르며 매도세가 소진되었음을 의미 (강력한 반등 신호)">
                      <Flame size={11} className="text-amber-400" />
                      OBV 세력 매집중 ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : c.obv_divergence > 1.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help" title="약한 수준의 세력 매집 시그널 포착">
                      OBV 매집 포착 ({c.obv_divergence.toFixed(0)}%)
                    </span>
                  ) : null}

                  {/* BB 스퀴즈 압착 강도 배지 */}
                  {c.bollinger_band_width_percentile <= 20.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-300 border border-zinc-700 px-2 py-1 rounded-lg cursor-help flex items-center gap-1" title="볼린저 밴드가 극도로 압착되어 조만간 폭발적인 추세가 나올 가능성 높음"><span className="text-indigo-400">🧭</span>
                      BB 대압착 (에너지 100% 장착)
                    </span>
                  ) : c.bollinger_band_width_percentile <= 40.0 ? (
                    <span className="bg-zinc-800/80 text-zinc-400 border border-zinc-700 px-2 py-1 rounded-lg cursor-help flex items-center gap-1" title="볼린저 밴드가 수축되며 방향성을 탐색 중"><span className="text-purple-400">🧭</span>
                      BB 수축 (에너지 충전중)
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

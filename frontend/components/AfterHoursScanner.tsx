'use client';

import React, { useCallback, useState } from 'react';
import useSWR from 'swr';
import { Activity, AlertTriangle, Moon, RefreshCw, ShieldCheck, Star, TrendingUp, Zap } from 'lucide-react';
import { toast } from 'sonner';

import { fetcher, scannerAPI } from '@/lib/api';
import { cn, reportHandledError } from '@/lib/utils';
import { useTimezone } from '@/store/timezoneStore';
import { ScannerTabs, type ScannerTab } from '@/components/ScannerTabs';

interface AfterHoursDetails {
  regular_change_pct: number;
  final_hour_return_pct: number;
  close_position_pct: number;
  vwap_distance_pct: number;
  regular_volume_ratio: number;
  after_hours_change_pct: number;
  after_hours_volume_ratio: number;
  after_hours_volume: number;
  regular_volume: number;
}

interface AfterHoursCandidate {
  ticker: string;
  name: string;
  source: string[];
  price: number;
  regular_close: number;
  score: number;
  signal_type: 'STRONG_AFTER_HOURS' | 'AFTER_HOURS_WATCH' | 'WATCH';
  reasons: string[];
  risk_flags: string[];
  catalyst_keywords: string[];
  session_date: string;
  details: AfterHoursDetails;
}

interface AfterHoursResponse {
  candidates: AfterHoursCandidate[];
  scope: 'global';
  sync_status: 'empty' | 'failed' | 'fresh' | 'refreshing' | 'stale';
  updated_at: string | null;
  universe_size: number;
}

interface AfterHoursScannerProps {
  activeTab?: ScannerTab;
  setActiveTab?: (tab: ScannerTab) => void;
  onAddToWatchlist?: (ticker: string, name: string) => Promise<void> | void;
  watchlistTickers?: string[];
}

const SIGNAL_LABEL = {
  STRONG_AFTER_HOURS: '강한 후보',
  AFTER_HOURS_WATCH: '관찰 후보',
  WATCH: '대기',
};

export function AfterHoursScanner({
  activeTab = 'after-hours',
  setActiveTab,
  onAddToWatchlist,
  watchlistTickers = [],
}: AfterHoursScannerProps) {
  const { data: swrData, isLoading, mutate } = useSWR('/scanner/after-hours-candidates', fetcher, {
    refreshInterval: 15000,
  });
  const payload: AfterHoursResponse = swrData || {
    candidates: [],
    scope: 'global',
    sync_status: 'empty',
    updated_at: null,
    universe_size: 0,
  };
  const [refreshing, setRefreshing] = useState(false);
  const [addingTicker, setAddingTicker] = useState<string | null>(null);
  const { selectedTimezone } = useTimezone();

  const handleAddToWatchlist = useCallback(async (ticker: string, name: string) => {
    setAddingTicker(ticker);
    try {
      await onAddToWatchlist?.(ticker, name);
    } catch {
      // The shared watchlist action reports the error.
    } finally {
      setAddingTicker(null);
    }
  }, [onAddToWatchlist]);

  const refreshCandidates = useCallback(async () => {
    setRefreshing(true);
    try {
      await scannerAPI.refreshAfterHoursCandidates();
      toast.info('에프터장 후보 스캔이 백그라운드에서 시작되었습니다.');
      setTimeout(async () => {
        await mutate();
        setRefreshing(false);
      }, 3000);
    } catch (error) {
      const msg = reportHandledError('Failed to refresh after-hours candidates', error);
      toast.error(`에프터장 후보 갱신 실패: ${msg}`);
      setRefreshing(false);
    }
  }, [mutate]);

  const status = refreshing ? 'refreshing' : payload.sync_status;
  const candidates = payload.candidates;

  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl shadow-xl overflow-hidden">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-5 border-b border-zinc-800/80">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <Moon size={21} />
          </div>
          <div>
            <h2 className="text-lg font-black text-white tracking-tight">에프터장 상승 후보</h2>
            <p className="text-xs text-zinc-500 font-medium">정규장 마감 품질과 에프터장 확인 신호를 분리 채점합니다.</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="text-[10px] bg-zinc-950 text-zinc-400 border border-zinc-800 font-mono px-3 py-1 rounded-full flex items-center gap-1.5">
            <span className={cn(
              'w-1.5 h-1.5 rounded-full',
              status === 'fresh' ? 'bg-emerald-500' :
              status === 'stale' ? 'bg-amber-500' :
              status === 'failed' ? 'bg-rose-500' :
              'bg-indigo-500 animate-pulse'
            )} />
            {status.toUpperCase()} · {payload.universe_size} TICKERS
          </span>
          {payload.updated_at && (
            <span className="text-[10px] text-zinc-500 font-mono flex items-center gap-1.5">
              <span className="bg-zinc-800/80 text-zinc-400 px-1.5 py-0.5 rounded font-black tracking-widest">{selectedTimezone.abbr}</span>
              {new Date(payload.updated_at).toLocaleTimeString('ko-KR', { timeZone: selectedTimezone.timeZone })}
            </span>
          )}
          <button
            onClick={() => refreshCandidates()}
            disabled={refreshing || status === 'refreshing'}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50 border border-zinc-700/50"
            title="정규장 흐름과 에프터장 체결 데이터를 다시 분석합니다"
          >
            <RefreshCw size={13} className={cn((refreshing || status === 'refreshing') && 'animate-spin text-emerald-400')} />
            {refreshing || status === 'refreshing' ? '갱신 중...' : '후보 갱신'}
          </button>
        </div>
      </div>

      <ScannerTabs activeTab={activeTab} setActiveTab={setActiveTab} />

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Activity size={36} className="animate-pulse mb-3 text-emerald-500/50" />
          <p className="text-sm font-bold">에프터장 후보 캐시를 불러오는 중입니다.</p>
        </div>
      ) : candidates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
          <Moon size={34} className="mb-3 text-zinc-700" />
          <p className="text-sm font-bold">저장된 에프터장 후보가 없습니다.</p>
          <p className="text-xs text-zinc-600 mt-2">미국 에프터장 시간에 후보 갱신을 실행하면 정규장 마감 이후 체결 흐름까지 반영합니다.</p>
        </div>
      ) : (
        <div className="overflow-auto custom-scrollbar">
          <table className="w-full min-w-[980px] text-left border-collapse">
            <thead>
              <tr className="border-b border-zinc-800/60 text-zinc-500 text-[10px] uppercase tracking-[0.1em]">
                <th className="py-4 px-5">Rank</th>
                <th className="py-4 px-3">Ticker</th>
                <th className="py-4 px-3 text-right">After Price</th>
                <th className="py-4 px-3 text-center">Regular Flow</th>
                <th className="py-4 px-3 text-center">After Confirm</th>
                <th className="py-4 px-3">Reasons</th>
                <th className="py-4 px-5 text-center">Score</th>
                <th className="py-4 px-5 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/40">
              {candidates.map((candidate, index) => {
                const strong = candidate.signal_type === 'STRONG_AFTER_HOURS';
                const watch = candidate.signal_type === 'AFTER_HOURS_WATCH';
                const isAdding = addingTicker === candidate.ticker;
                const isInWatchlist = watchlistTickers.includes(candidate.ticker.toUpperCase());
                return (
                  <tr key={candidate.ticker} className={cn('hover:bg-white/[0.025] transition-colors', strong && 'bg-emerald-500/[0.025]')}>
                    <td className="py-4 px-5 text-xs font-mono text-zinc-600">{String(index + 1).padStart(2, '0')}</td>
                    <td className="py-4 px-3">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-black text-white">{candidate.ticker}</span>
                          <span className={cn(
                            'text-[9px] px-1.5 py-0.5 rounded border font-black',
                            strong ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' :
                            watch ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' :
                            'bg-zinc-800 text-zinc-500 border-zinc-700'
                          )}>
                            {SIGNAL_LABEL[candidate.signal_type]}
                          </span>
                        </div>
                        <span className="text-[11px] text-zinc-500 font-medium truncate max-w-[180px]">{candidate.name}</span>
                        <span className="text-[10px] text-zinc-600 font-mono">{candidate.session_date}</span>
                      </div>
                    </td>
                    <td className="py-4 px-3 text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span className="text-sm text-zinc-200 font-mono font-bold">${candidate.price.toFixed(2)}</span>
                        <span className="text-[10px] text-zinc-600 font-mono">Close ${candidate.regular_close.toFixed(2)}</span>
                      </div>
                    </td>
                    <td className="py-4 px-3">
                      <div className="flex flex-col items-center gap-1.5 text-[11px] font-bold">
                        <span className={candidate.details.regular_change_pct >= 0 ? 'text-rose-400' : 'text-blue-400'}>
                          정규장 {candidate.details.regular_change_pct >= 0 ? '+' : ''}{candidate.details.regular_change_pct}%
                        </span>
                        <span className="text-zinc-400">마감 1h {candidate.details.final_hour_return_pct >= 0 ? '+' : ''}{candidate.details.final_hour_return_pct}%</span>
                        <span className="text-zinc-500">고가권 {candidate.details.close_position_pct}%</span>
                      </div>
                    </td>
                    <td className="py-4 px-3">
                      <div className="flex flex-col items-center gap-1.5 text-[11px] font-bold">
                        <span className={candidate.details.after_hours_change_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                          에프터 {candidate.details.after_hours_change_pct >= 0 ? '+' : ''}{candidate.details.after_hours_change_pct}%
                        </span>
                        <span className="text-zinc-400">거래량비 {(candidate.details.after_hours_volume_ratio * 100).toFixed(1)}%</span>
                        <span className="text-zinc-600 font-mono">{candidate.details.after_hours_volume.toLocaleString()}주</span>
                      </div>
                    </td>
                    <td className="py-4 px-3">
                      <div className="flex flex-wrap gap-1.5 max-w-[300px]">
                        {candidate.reasons.slice(0, 4).map((reason) => (
                          <span key={reason} className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-[10px] font-bold">
                            <ShieldCheck size={10} />
                            {reason}
                          </span>
                        ))}
                        {candidate.catalyst_keywords.map((keyword) => (
                          <span key={keyword} className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 text-[10px] font-bold">
                            <Zap size={10} />
                            {keyword}
                          </span>
                        ))}
                        {candidate.risk_flags.slice(0, 3).map((flag) => (
                          <span key={flag} className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/20 text-[10px] font-bold">
                            <AlertTriangle size={10} />
                            {flag}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-4 px-5">
                      <div className="flex flex-col items-center gap-1.5">
                        <div className="w-24 h-2 bg-zinc-950 rounded-full overflow-hidden border border-zinc-800">
                          <div
                            className={cn('h-full transition-all duration-1000', strong ? 'bg-emerald-500' : watch ? 'bg-amber-500' : 'bg-zinc-500')}
                            style={{ width: `${candidate.score}%` }}
                          />
                        </div>
                        <span className={cn('text-xs font-black font-mono flex items-center gap-1', strong ? 'text-emerald-400' : watch ? 'text-amber-400' : 'text-zinc-500')}>
                          <TrendingUp size={13} />
                          {candidate.score}
                        </span>
                      </div>
                    </td>
                    <td className="py-4 px-5 text-center">
                      <button
                        onClick={() => handleAddToWatchlist(candidate.ticker, candidate.name)}
                        disabled={isAdding || isInWatchlist || !onAddToWatchlist}
                        className={cn(
                          "inline-flex items-center gap-1.5 px-2.5 py-1.5 border rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50",
                          isInWatchlist
                            ? "bg-zinc-800/70 text-zinc-400 border-zinc-700"
                            : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
                        )}
                        title="관심종목에 등록합니다"
                      >
                        {isAdding ? (
                          <RefreshCw size={13} className="animate-spin" />
                        ) : (
                          <Star size={13} className="fill-emerald-400/20" />
                        )}
                        <span>{isInWatchlist ? '등록됨' : '관심등록'}</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

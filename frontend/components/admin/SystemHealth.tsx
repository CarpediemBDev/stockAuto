'use client';

import React, { useState } from 'react';
import { Terminal, Clock, Loader2, Server, Activity, Smartphone, Search, Globe, Database } from 'lucide-react';
import { reportAPI } from '@/lib/api';
import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { toast } from "sonner";
import { cn, reportHandledError } from '@/lib/utils';
import { useTimezone } from '@/store/timezoneStore';

interface ActionLog {
  id: number;
  level: string;
  message: string;
  created_at: string;
}

export function SystemHealth() {
  const { data: swrData, isLoading } = useSWR('/admin/system-logs', fetcher, { refreshInterval: 15000 });
  const logs: ActionLog[] = Array.isArray(swrData) ? swrData : (swrData?.data || []);
  const loading = isLoading;

  const { data: statsData } = useSWR('/admin/discovery-stats', fetcher, { refreshInterval: 15000 });
  const stats = statsData || {
    last_run: null,
    status: 'IDLE',
    toss: { count: 0, status: 'PENDING' },
    yahoo: { count: 0, status: 'PENDING' },
    naver: { count: 0, status: 'PENDING' },
    total_universe: 0
  };

  const [isReportSending, setIsReportSending] = useState(false);
  const [isGlobalReportSending, setIsGlobalReportSending] = useState(false);
  const { selectedTimezone } = useTimezone();

  const handleTriggerManualReport = async () => {
    try {
      setIsReportSending(true);
      const res = await reportAPI.triggerManualReport();
      toast.success(res.serverMessage || "관리자 본인의 텔레그램 일일 결산 리포트 발송에 성공했습니다.");
    } catch (error) {
      const msg = reportHandledError("Failed to trigger manual report", error);
      toast.error(`리포트 발송 실패: ${msg}`);
    } finally {
      setIsReportSending(false);
    }
  };

  const handleTriggerGlobalReport = async () => {
    try {
      setIsGlobalReportSending(true);
      const res = await reportAPI.triggerGlobalReport();
      toast.success(res.serverMessage || "전체 사용자의 텔레그램 리포트 발송이 완료되었습니다.");
    } catch (error) {
      const msg = reportHandledError("Failed to trigger global report", error);
      toast.error(`전체 리포트 발송 실패: ${msg}`);
    } finally {
      setIsGlobalReportSending(false);
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'SIGNAL': return 'text-amber-400';
      case 'ERROR': return 'text-rose-500';
      case 'WARN': return 'text-orange-400';
      case 'SUCCESS': return 'text-emerald-400';
      default: return 'text-slate-400';
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Server size={18} className="text-blue-400" />
            시스템 헬스 실시간 모니터링
          </h2>
          <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
            REALTIME POLLING
          </span>
        </div>

        {/* 시스템 관리 수동 제어 센터 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 my-2">
          <div className="bg-slate-950/50 border border-zinc-800/60 rounded-2xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full"></span>
                수동 결산 및 리포트 즉시 발송
              </h3>
              <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">
                현재 로그인된 관리자 본인에 한해 손익 및 거래 현황을 즉시 집계하여, 본인의 텔레그램 채널로 결산 보고서를 즉시 발송합니다. (테스트 목적)
              </p>
            </div>
            <div className="flex items-center justify-end space-x-2">
              <button
                onClick={handleTriggerManualReport}
                disabled={isReportSending || isGlobalReportSending}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-bold transition-all duration-300 border flex items-center gap-2 shadow-lg",
                  isReportSending
                    ? "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed"
                    : "bg-indigo-950/60 text-indigo-300 border-indigo-900/60 hover:bg-indigo-900/60 hover:text-white active:scale-95 shadow-indigo-950/20"
                )}
              >
                {isReportSending ? (
                  <>
                    <Loader2 size={12} className="animate-spin text-zinc-500" />
                    내게 테스트 발송 중...
                  </>
                ) : (
                  <>
                    <span>📨 내게 테스트 발송</span>
                  </>
                )}
              </button>
              
              <button
                onClick={handleTriggerGlobalReport}
                disabled={isReportSending || isGlobalReportSending}
                className={cn(
                  "px-4 py-2 rounded-xl text-xs font-bold transition-all duration-300 border flex items-center gap-2 shadow-lg",
                  isGlobalReportSending
                    ? "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed"
                    : "bg-emerald-950/60 text-emerald-300 border-emerald-900/60 hover:bg-emerald-900/60 hover:text-white active:scale-95 shadow-emerald-950/20"
                )}
              >
                {isGlobalReportSending ? (
                  <>
                    <Loader2 size={12} className="animate-spin text-zinc-500" />
                    전체 발송 중...
                  </>
                ) : (
                  <>
                    <span>🚀 전체 사용자 발송</span>
                  </>
                )}
              </button>
            </div>
          </div>

          <div className="bg-slate-950/50 border border-zinc-800/60 rounded-2xl p-4 flex flex-col justify-between space-y-3">
            <div>
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>
                시스템 데이터 동기화
              </h3>
              <div className="grid grid-cols-2 gap-2 mt-2">
                <div className="bg-zinc-900/40 p-2 rounded-lg border border-zinc-800/40 text-center">
                  <span className="text-[10px] text-zinc-500 block">시스템 로그 수신</span>
                  <span className="text-xs font-bold text-slate-300">{logs.length}개 갱신됨</span>
                </div>
                <div className="bg-zinc-900/40 p-2 rounded-lg border border-zinc-800/40 text-center">
                  <span className="text-[10px] text-zinc-500 block">통신 감도</span>
                  <span className="text-xs font-bold text-emerald-400">네트워크 정상</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 크롤링 모니터링 대시보드 */}
        <div className="bg-slate-950/80 border border-zinc-800/80 rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Activity size={16} className="text-pink-400" />
              크롤링 엔진 모니터링 (Discovery Stats)
            </h3>
            <span className={cn(
              "text-[10px] font-bold px-2 py-0.5 rounded flex items-center gap-1.5",
              stats.status === 'RUNNING' ? 'bg-amber-500/20 text-amber-400' :
              stats.status === 'ERROR' ? 'bg-rose-500/20 text-rose-400' :
              'bg-emerald-500/20 text-emerald-400'
            )}>
              <span className={cn(
                "w-1.5 h-1.5 rounded-full",
                stats.status === 'RUNNING' ? 'bg-amber-400 animate-pulse' :
                stats.status === 'ERROR' ? 'bg-rose-500' :
                'bg-emerald-500'
              )}></span>
              {stats.status}
            </span>
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* 토스증권 카드 */}
            <div className="bg-zinc-900/40 p-3 rounded-xl border border-zinc-800/40 flex items-center space-x-3">
              <div className={cn("p-2 rounded-lg", stats.toss.status === 'ERROR' ? 'bg-rose-500/10 text-rose-400' : 'bg-blue-500/10 text-blue-400')}>
                <Smartphone size={18} />
              </div>
              <div>
                <span className="text-[10px] text-zinc-500 block font-semibold uppercase tracking-wider">Toss Securities</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-lg font-bold", stats.toss.status === 'ERROR' ? 'text-rose-400' : 'text-slate-200')}>
                    {stats.toss.status === 'ERROR' ? 'FAIL' : stats.toss.count}
                  </span>
                  {stats.toss.status === 'SUCCESS' && <span className="text-[9px] text-zinc-500">종목</span>}
                </div>
              </div>
            </div>

            {/* 네이버증권 카드 */}
            <div className="bg-zinc-900/40 p-3 rounded-xl border border-zinc-800/40 flex items-center space-x-3">
              <div className={cn("p-2 rounded-lg", stats.naver.status === 'ERROR' ? 'bg-rose-500/10 text-rose-400' : 'bg-green-500/10 text-green-400')}>
                <Search size={18} />
              </div>
              <div>
                <span className="text-[10px] text-zinc-500 block font-semibold uppercase tracking-wider">Naver Finance</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-lg font-bold", stats.naver.status === 'ERROR' ? 'text-rose-400' : 'text-slate-200')}>
                    {stats.naver.status === 'ERROR' ? 'FAIL' : stats.naver.count}
                  </span>
                  {stats.naver.status === 'SUCCESS' && <span className="text-[9px] text-zinc-500">종목</span>}
                </div>
              </div>
            </div>

            {/* 야후파이낸스 카드 */}
            <div className="bg-zinc-900/40 p-3 rounded-xl border border-zinc-800/40 flex items-center space-x-3">
              <div className={cn("p-2 rounded-lg", stats.yahoo.status === 'ERROR' ? 'bg-rose-500/10 text-rose-400' : 'bg-purple-500/10 text-purple-400')}>
                <Globe size={18} />
              </div>
              <div>
                <span className="text-[10px] text-zinc-500 block font-semibold uppercase tracking-wider">Yahoo Finance</span>
                <div className="flex items-center gap-2">
                  <span className={cn("text-lg font-bold", stats.yahoo.status === 'ERROR' ? 'text-rose-400' : 'text-slate-200')}>
                    {stats.yahoo.status === 'ERROR' ? 'FAIL' : stats.yahoo.count}
                  </span>
                  {stats.yahoo.status === 'SUCCESS' && <span className="text-[9px] text-zinc-500">종목</span>}
                </div>
              </div>
            </div>

            {/* 통합 유니버스 카드 */}
            <div className="bg-zinc-900/60 p-3 rounded-xl border border-indigo-500/20 flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
                <Database size={18} />
              </div>
              <div>
                <span className="text-[10px] text-indigo-400/80 block font-semibold uppercase tracking-wider">Merged Universe</span>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-indigo-300">
                    {stats.total_universe}
                  </span>
                  <span className="text-[9px] text-indigo-500/60">최종 분석 풀</span>
                </div>
              </div>
            </div>
          </div>
          
          {stats.last_run && (
            <div className="text-[10px] text-zinc-500 flex items-center justify-end">
              최근 업데이트: {new Date(stats.last_run).toLocaleTimeString('ko-KR', {
                timeZone: selectedTimezone.timeZone,
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
              })}
            </div>
          )}
        </div>
        
        
        <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col h-[500px]">
          <div className="bg-slate-900/80 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Terminal size={14} className="text-emerald-500" />
              <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">Admin Debug Console</span>
            </div>
            <div className="flex space-x-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[12px] scrollbar-thin scrollbar-thumb-slate-800">
            {loading && logs.length === 0 ? (
              <div className="py-20 flex flex-col items-center justify-center gap-3">
                <Loader2 size={36} className="animate-spin text-zinc-500" />
                <span className="text-xs text-zinc-500 font-semibold">로그 데이터 로딩 중...</span>
              </div>
            ) : logs.length === 0 ? (
              <div className="text-slate-700 italic">No system activity recorded yet.</div>
            ) : (
              logs.map((log) => (
                <div key={log.id} className="flex items-start space-x-3 group border-l-2 border-transparent hover:border-slate-800 pl-2 transition-colors">
                  <span className="text-slate-600 shrink-0 flex items-center gap-1 select-none">
                    <Clock size={10} className="mr-0.5" />
                    <span className="text-[9px] bg-slate-900 text-slate-500 px-1.5 py-0.5 rounded font-bold tracking-widest mr-1">
                      {selectedTimezone.abbr}
                    </span>
                    {new Date(log.created_at).toLocaleTimeString('ko-KR', {
                      timeZone: selectedTimezone.timeZone,
                      hour12: false,
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit'
                    })}
                  </span>
                  <span className={cn("font-bold shrink-0 w-16", getLevelColor(log.level))}>
                    [{log.level}]
                  </span>
                  <span className="text-slate-300 break-all">{log.message}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

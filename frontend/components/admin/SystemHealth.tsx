'use client';

import React, { useState, useCallback } from 'react';
import { Terminal, Clock, Loader2, Server } from 'lucide-react';
import { adminAPI, reportAPI, isCancel } from '@/lib/api';
import { usePolling } from '@/hooks/usePolling';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';
import { cn } from '@/lib/utils';

interface ActionLog {
  id: number;
  level: string;
  message: string;
  created_at: string;
}

export function SystemHealth() {
  const [logs, setLogs] = useState<ActionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [isReportSending, setIsReportSending] = useState(false);

  const handleTriggerManualReport = async () => {
    try {
      setIsReportSending(true);
      await reportAPI.triggerManualReport();
      toast.success("텔레그램 일일 결산 리포트 발송에 성공했습니다.");
    } catch (error) {
      const msg = getErrorMessage(error);
      console.error("Failed to trigger manual report:", msg);
      toast.error(`리포트 발송 실패: ${msg}`);
    } finally {
      setIsReportSending(false);
    }
  };

  const fetchLogs = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await adminAPI.getSystemLogs({ signal });
      setLogs(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error('Failed to fetch system logs:', msg);
      toast.error(`시스템 로그 갱신 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, []);

  usePolling(fetchLogs, 5000);

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
                모든 활성 사용자(admin~admin10)에 대해 현재까지의 손익 및 거래 현황을 즉시 집계하여 등록된 모든 텔레그램 채널로 일일 결산 보고서를 즉시 발송합니다.
              </p>
            </div>
            <div className="flex items-center justify-end">
              <button
                onClick={handleTriggerManualReport}
                disabled={isReportSending}
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
                    정산 및 리포트 발송 중...
                  </>
                ) : (
                  <>
                    <span>📨 리포트 즉시 발송</span>
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
                  <span className="text-slate-600 shrink-0 flex items-center">
                    <Clock size={10} className="mr-1" />
                    {new Date(log.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
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

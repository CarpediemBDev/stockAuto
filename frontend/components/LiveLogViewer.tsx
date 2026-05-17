'use client';

import React, { useState, useCallback } from 'react';
import { Terminal, Clock } from 'lucide-react';
import { tradeAPI, isCancel } from '@/lib/api';
import { usePolling } from '@/hooks/usePolling';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

interface ActionLog {
  id: number;
  level: string;
  message: string;
  created_at: string;
}

const LiveLogViewer = () => {
  const [logs, setLogs] = useState<ActionLog[]>([]);

  const fetchLogs = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await tradeAPI.getActions({ signal });
      setLogs(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error('Failed to fetch action logs:', msg);
      toast.error(`로그 갱신 실패: ${msg}`);
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
    <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col h-[400px]">
      <div className="bg-slate-900/80 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Terminal size={14} className="text-emerald-500" />
          <span className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">Bot Execution Logs</span>
        </div>
        <div className="flex space-x-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
          <div className="w-2.5 h-2.5 rounded-full bg-slate-800"></div>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[12px] scrollbar-thin scrollbar-thumb-slate-800">
        {logs.length === 0 ? (
          <div className="text-slate-700 italic">Waiting for bot activity...</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="flex items-start space-x-3 group border-l-2 border-transparent hover:border-slate-800 pl-2 transition-colors">
              <span className="text-slate-600 shrink-0 flex items-center">
                <Clock size={10} className="mr-1" />
                {new Date(log.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className={`font-bold shrink-0 w-16 ${getLevelColor(log.level)}`}>
                [{log.level}]
              </span>
              <span className="text-slate-300 break-all">{log.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LiveLogViewer;

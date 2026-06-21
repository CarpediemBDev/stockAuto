'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  TrendingUp, Target, Activity, DollarSign
} from 'lucide-react';
import { reportAPI, tradeAPI } from '@/lib/api';
import { TradeLogs, TradeLog } from '@/components/TradeLogs';
import { reportHandledError } from '@/lib/utils';

interface TradeItem {
  id: number;
  date: string;
  time: string;
  ticker: string;
  ticker_name: string | null;
  realized_pnl: number;
  return_rate: number;
  cumulative_pnl: number;
}

interface StatsData {
  kpi: {
    total_trades: number;
    win_trades: number;
    loss_trades: number;
    total_realized_pnl: number;
    gross_profit: number;
    gross_loss: number;
    win_rate: number;
    profit_factor: number;
  };
  chart_data: TradeItem[];
}

export default function ReportPage() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [logs, setLogs] = useState<TradeLog[]>([]);

  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.push('/login');
    }
  }, [isInitialized, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) return;

    let isMounted = true;
    async function fetchStatsAndLogs() {
      try {
        const [statsRes, logsRes] = await Promise.all([
          reportAPI.getStats(),
          tradeAPI.getLogs()
        ]);
        if (isMounted) {
          setStats(statsRes.data);
          setLogs(logsRes.data);
          setLoading(false);
        }
      } catch (error) {
        reportHandledError("Failed to fetch report stats or logs", error);
        if (isMounted) setLoading(false);
      }
    }

    fetchStatsAndLogs();
    return () => { isMounted = false; };
  }, [isAuthenticated]);

  if (!isInitialized || !isAuthenticated || loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex justify-center items-center h-64 text-slate-500">
        <Activity className="w-6 h-6 mr-2 opacity-50" />
        데이터를 불러오지 못했습니다.
      </div>
    );
  }

  const { kpi, chart_data } = stats;
  const isProfitable = kpi.total_realized_pnl >= 0;

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-[1600px] mx-auto px-6 py-8 md:py-12 space-y-8 animate-in fade-in duration-500">
        
        {/* Header */}
        <header className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-zinc-800 pb-5">
          <div>
            <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-zinc-200 to-zinc-400 tracking-tight mb-2">
              종합 매매 성적표
            </h1>
            <p className="text-zinc-400 font-medium tracking-wide">
              계좌의 전체 누적 수익금과 승률 등 핵심 투자 성과를 분석합니다.
            </p>
          </div>
          <div className="flex items-center space-x-2 text-xs font-bold text-zinc-300 bg-zinc-900/50 px-4 py-2 rounded-lg border border-zinc-800">
            <div className="relative flex h-2 w-2 mr-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </div>
            <span>실시간 라이브 데이터 동기화</span>
          </div>
        </header>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

        {/* Total PnL */}
        <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-600 transition-colors duration-300">
          <div className="flex flex-col justify-between h-full space-y-4">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="font-bold text-xs tracking-wider uppercase">총 실수익금</span>
              <DollarSign className="w-5 h-5 text-zinc-500" />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline space-x-1">
                <span className={`text-4xl font-extrabold tracking-tight ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                  ${kpi.total_realized_pnl.toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs font-bold tracking-tight mt-1.5">
                <span className="text-emerald-300 bg-emerald-500/15 px-2 py-0.5 rounded-md border border-emerald-500/30">
                  총수익: <span className="font-mono">${(kpi.gross_profit || 0).toLocaleString()}</span>
                </span>
                <span className="text-rose-300 bg-rose-500/15 px-2 py-0.5 rounded-md border border-rose-500/30">
                  총손실: <span className="font-mono">${(kpi.gross_loss || 0).toLocaleString()}</span>
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Win Rate */}
        <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-600 transition-colors duration-300">
          <div className="flex flex-col justify-between h-full space-y-4">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="font-bold text-xs tracking-wider uppercase">승률 (Win Rate)</span>
              <Target className="w-5 h-5 text-zinc-500" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-4xl font-extrabold tracking-tight text-white">
                {kpi.win_rate}%
              </span>
            </div>
          </div>
        </div>

        {/* Profit Factor */}
        <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-600 transition-colors duration-300">
          <div className="flex flex-col justify-between h-full space-y-4">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="font-bold text-xs tracking-wider uppercase">프로핏 팩터</span>
              <TrendingUp className="w-5 h-5 text-zinc-500" />
            </div>
            <div className="flex items-baseline space-x-1">
              <span className="text-4xl font-extrabold tracking-tight text-white">
                {kpi.profit_factor}
              </span>
            </div>
          </div>
        </div>

        {/* Total Trades */}
        <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-600 transition-colors duration-300">
          <div className="flex flex-col justify-between h-full space-y-4">
            <div className="flex items-center justify-between text-zinc-400">
              <span className="font-bold text-xs tracking-wider uppercase">총 거래 횟수</span>
              <Activity className="w-5 h-5 text-zinc-500" />
            </div>
            <div className="flex flex-col gap-1">
              <div className="flex items-baseline space-x-1">
                <span className="text-4xl font-extrabold tracking-tight text-white">
                  {kpi.total_trades}
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs font-bold tracking-tight mt-1.5">
                <span className="text-emerald-300 bg-emerald-500/15 px-2 py-0.5 rounded-md border border-emerald-500/30">
                  익절: <span className="font-mono">{kpi.win_trades || 0}</span>회
                </span>
                <span className="text-rose-300 bg-rose-500/15 px-2 py-0.5 rounded-md border border-rose-500/30">
                  손절: <span className="font-mono">{kpi.loss_trades || 0}</span>회
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chart Area */}
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 md:p-8 shadow-xl">
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          <TrendingUp className="w-5 h-5 text-zinc-400" />
          <span>누적 수익 곡선 <span className="text-zinc-500 font-normal ml-1 text-sm">Cumulative Profit</span></span>
        </h2>
        <div className="h-96 min-h-96 w-full min-w-0 overflow-hidden">
          {chart_data.length > 0 ? (
            <ResponsiveContainer width="100%" height={384} minWidth={0} minHeight={240}>
              <AreaChart data={chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPnL" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={isProfitable ? '#10b981' : '#f43f5e'} stopOpacity={0.4} />
                    <stop offset="95%" stopColor={isProfitable ? '#10b981' : '#f43f5e'} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#94a3b8"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickMargin={12}
                />
                <YAxis
                  stroke="#94a3b8"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(val) => `$${val}`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '12px', color: '#fff', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)' }}
                  itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '8px' }}
                />
                <Area
                  type="monotone"
                  dataKey="cumulative_pnl"
                  name="누적 실수익금"
                  stroke={isProfitable ? '#10b981' : '#f43f5e'}
                  strokeWidth={4}
                  fillOpacity={1}
                  fill="url(#colorPnL)"
                  animationDuration={1500}
                  animationEasing="ease-out"
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-slate-500">
              <Activity className="w-12 h-12 mb-4 opacity-50" />
              <p>아직 매도 내역(수익 실현)이 없습니다.</p>
            </div>
          )}
        </div>
      </div>

      {/* 실시간 체결 로그 팝업 메뉴 버튼 */}
      <div className="flex justify-center pt-4 pb-8">
        <button
          onClick={() => setIsLogsModalOpen(true)}
          className="bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-6 py-3 rounded-xl border border-zinc-700 font-semibold transition-all duration-300 flex items-center gap-2 active:scale-95 shadow-lg"
        >
          <Activity className="w-4 h-4 text-zinc-400" />
          <span>실시간 체결 로그 전체보기</span>
        </button>
      </div>

      {/* 미니멀 다크 모달 */}
      {isLogsModalOpen && (
        <div
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsLogsModalOpen(false);
          }}
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-300"
        >
          <div className="bg-[#090d16] border border-zinc-800 rounded-2xl max-w-5xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-300 overflow-hidden max-h-[85vh] flex flex-col">
            {/* 닫기 버튼 */}
            <button
              onClick={() => setIsLogsModalOpen(false)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-white p-2 rounded-lg hover:bg-zinc-800 active:scale-95 transition-all z-10 font-bold"
              aria-label="닫기"
            >
              ✕
            </button>

            {/* 거래 내역 테이블 로드 */}
            <div className="flex-1 mt-2 overflow-y-auto custom-scrollbar">
              <TradeLogs logs={logs} isModalMode={true} />
            </div>
          </div>
        </div>
      )}

      </div>
    </div>
  );
}

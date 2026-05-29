'use client';

import { useEffect, useState, startTransition } from 'react';
import { useRouter } from 'next/navigation';
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from 'recharts';
import { 
  TrendingUp, Target, Activity, DollarSign, ArrowUpRight, ArrowDownRight
} from 'lucide-react';
import { reportAPI, tradeAPI } from '@/lib/api';
import { TradeLogs, TradeLog } from '@/components/TradeLogs';

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
    total_realized_pnl: number;
    win_rate: number;
    profit_factor: number;
  };
  chart_data: TradeItem[];
}

export default function ReportPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [logs, setLogs] = useState<TradeLog[]>([]);

  useEffect(() => {
    const token = localStorage.getItem('stockauto_token');
    if (!token) {
      router.push('/login');
    } else {
      startTransition(() => setIsAuthenticated(true));
    }
  }, [router]);

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
        console.error("Failed to fetch report stats or logs", error);
        if (isMounted) setLoading(false);
      }
    }
    
    fetchStatsAndLogs();
    return () => { isMounted = false; };
  }, [isAuthenticated]);

  if (!isAuthenticated || loading) {
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
    <div className="space-y-6 animate-in fade-in zoom-in duration-500">
      
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400 tracking-tight">
          종합 매매 성적표 (Trading Performance)
        </h1>
        <div className="flex items-center space-x-2 text-sm text-slate-400">
          <Activity className="w-4 h-4 text-emerald-500 animate-pulse" />
          <span>실시간 라이브 데이터 동기화</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Total PnL */}
        <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700/50 p-6 rounded-2xl relative overflow-hidden group">
          <div className={`absolute top-0 right-0 w-32 h-32 bg-gradient-to-br ${isProfitable ? 'from-emerald-500/10 to-teal-500/0' : 'from-rose-500/10 to-pink-500/0'} rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150 duration-700`}></div>
          <div className="relative z-10 flex flex-col justify-between h-full">
            <div className="flex items-center space-x-2 text-slate-400 mb-4">
              <DollarSign className="w-5 h-5" />
              <span className="font-semibold text-sm tracking-wide uppercase">총 실수익금 (세전/비용후)</span>
            </div>
            <div className="flex items-baseline space-x-2">
              <span className={`text-4xl font-black tracking-tighter ${isProfitable ? 'text-emerald-400' : 'text-rose-400'}`}>
                ${kpi.total_realized_pnl.toLocaleString()}
              </span>
            </div>
          </div>
        </div>

        {/* Win Rate */}
        <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700/50 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-indigo-500/10 to-blue-500/0 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150 duration-700"></div>
          <div className="relative z-10 flex flex-col justify-between h-full">
            <div className="flex items-center space-x-2 text-slate-400 mb-4">
              <Target className="w-5 h-5 text-indigo-400" />
              <span className="font-semibold text-sm tracking-wide uppercase">승률 (Win Rate)</span>
            </div>
            <div className="flex items-baseline space-x-2">
              <span className="text-4xl font-black tracking-tighter text-white">
                {kpi.win_rate}%
              </span>
            </div>
          </div>
        </div>

        {/* Profit Factor */}
        <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700/50 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-amber-500/10 to-orange-500/0 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150 duration-700"></div>
          <div className="relative z-10 flex flex-col justify-between h-full">
            <div className="flex items-center space-x-2 text-slate-400 mb-4">
              <TrendingUp className="w-5 h-5 text-amber-400" />
              <span className="font-semibold text-sm tracking-wide uppercase">프로핏 팩터 (손익비)</span>
            </div>
            <div className="flex items-baseline space-x-2">
              <span className="text-4xl font-black tracking-tighter text-white">
                {kpi.profit_factor}
              </span>
            </div>
          </div>
        </div>

        {/* Total Trades */}
        <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700/50 p-6 rounded-2xl relative overflow-hidden group">
          <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-cyan-500/10 to-blue-500/0 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150 duration-700"></div>
          <div className="relative z-10 flex flex-col justify-between h-full">
            <div className="flex items-center space-x-2 text-slate-400 mb-4">
              <Activity className="w-5 h-5 text-cyan-400" />
              <span className="font-semibold text-sm tracking-wide uppercase">총 매매 거래 횟수</span>
            </div>
            <div className="flex items-baseline space-x-2">
              <span className="text-4xl font-black tracking-tighter text-white">
                {kpi.total_trades}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Chart Area */}
      <div className="bg-slate-900/60 backdrop-blur-xl border border-slate-700/50 p-6 rounded-3xl shadow-2xl">
        <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
          <TrendingUp className="w-5 h-5 text-emerald-400" />
          <span>누적 수익 곡선 (Cumulative Profit)</span>
        </h2>
        <div className="h-96 w-full">
          {chart_data.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
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

      {/* 실시간 체결 로그 팝업 메뉴 버튼 (그래프 바로 밑에 배치) */}
      <div className="flex justify-center pt-2">
        <button
          onClick={() => setIsLogsModalOpen(true)}
          className="bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white px-6 py-3 rounded-2xl border border-slate-700/60 text-xs font-bold transition-all duration-300 flex items-center gap-2 active:scale-95 shadow-lg group hover:border-emerald-500/40"
        >
          <Activity className="w-4 h-4 text-emerald-400 animate-pulse group-hover:scale-110 transition-transform" />
          실시간 체결 로그 (Execution Logs) 팝업 조회
        </button>
      </div>

      {/* 프리미엄 다크 글래스모피즘 모달 (전체 거래 내역 상세 조회) */}
      {isLogsModalOpen && (
        <div 
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsLogsModalOpen(false);
          }}
          className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-in fade-in duration-300"
        >
          <div className="bg-zinc-950 border border-zinc-800 rounded-3xl max-w-5xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-300 overflow-hidden max-h-[85vh] flex flex-col">
            {/* 닫기 버튼 */}
            <button 
              onClick={() => setIsLogsModalOpen(false)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-white p-2 rounded-full hover:bg-zinc-900 active:scale-95 transition-all z-10 font-bold"
              aria-label="닫기"
            >
              ✕
            </button>

            {/* 거래 내역 테이블 로드 (모달 모드로 테두리 투명화) */}
            <div className="overflow-y-auto pr-1">
              <TradeLogs logs={logs} isModalMode={true} />
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

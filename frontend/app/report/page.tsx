'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  TrendingUp, Target, Activity, DollarSign, Percent
} from 'lucide-react';
import { reportAPI, tradeAPI } from '@/lib/api';
import { TradeLogs, TradeLog } from '@/components/TradeLogs';
import { reportHandledError } from '@/lib/utils';
import { Button, Modal } from '@/components/ui';
import { chartColors, getProfitColor } from '@/lib/theme';
import { useTranslations } from 'next-intl';

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
    max_drawdown_pct?: number;
  };
  chart_data: TradeItem[];
}

export default function ReportPage() {
  const t = useTranslations('report');
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
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-zinc-400 font-medium text-sm">{t('loading')}</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)]">
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 px-6 py-4 rounded-xl text-sm font-medium">
          {t('load_failed')}
        </div>
      </div>
    );
  }

  const { kpi, chart_data } = stats;
  const isProfitable = kpi.total_realized_pnl >= 0;

  return (
    <div className="min-h-screen text-slate-100 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1600px] mx-auto space-y-8">
        
        {/* Header */}
        <header className="flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-zinc-800/80 gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-white tracking-tight flex items-center gap-3">
              <span className="bg-indigo-600 w-3 h-8 rounded-full"></span>
              {t('title')}
            </h1>
            <p className="text-zinc-400 text-sm mt-1">{t('subtitle')}</p>
          </div>
          <div className="flex items-center space-x-2 text-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-full w-fit">
            <div className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </div>
            <span>{t('live_sync')}</span>
          </div>
        </header>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">

          {/* Total PnL */}
          <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-700 transition-colors duration-300">
            <div className="flex flex-col justify-between h-full space-y-4">
              <div className="flex items-center justify-between text-zinc-400">
                <span className="font-bold text-xs tracking-wider uppercase">{t('net_profit')}</span>
                <DollarSign className="w-5 h-5 text-zinc-500" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-baseline space-x-1">
                  <span className={`text-4xl font-extrabold tracking-tight ${getProfitColor(kpi.total_realized_pnl)}`}>
                    ${kpi.total_realized_pnl.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs font-bold tracking-tight mt-1.5">
                  <span className="text-emerald-300 bg-emerald-500/15 px-2 py-0.5 rounded-md border border-emerald-500/30">
                    {t('gross_profit')} <span className="font-mono">${(kpi.gross_profit || 0).toLocaleString()}</span>
                  </span>
                  <span className="text-rose-300 bg-rose-500/15 px-2 py-0.5 rounded-md border border-rose-500/30">
                    {t('gross_loss')} <span className="font-mono">${(kpi.gross_loss || 0).toLocaleString()}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Win Rate */}
          <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-700 transition-colors duration-300">
            <div className="flex flex-col justify-between h-full space-y-4">
              <div className="flex items-center justify-between text-zinc-400">
                <span className="font-bold text-xs tracking-wider uppercase">{t('win_rate')}</span>
                <Target className="w-5 h-5 text-zinc-500" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-baseline space-x-1">
                  <span className="text-4xl font-extrabold tracking-tight text-white">
                    {kpi.win_rate}%
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs font-bold tracking-tight mt-1.5">
                  <span className="text-emerald-300 bg-emerald-500/15 px-2 py-0.5 rounded-md border border-emerald-500/30">
                    {t('wins')} <span className="font-mono">{kpi.win_trades || 0}</span>{t('count_suffix')}
                  </span>
                  <span className="text-rose-300 bg-rose-500/15 px-2 py-0.5 rounded-md border border-rose-500/30">
                    {t('losses')} <span className="font-mono">{kpi.loss_trades || 0}</span>{t('count_suffix')}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Profit Factor */}
          <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-700 transition-colors duration-300">
            <div className="flex flex-col justify-between h-full space-y-4">
              <div className="flex items-center justify-between text-zinc-400">
                <span className="font-bold text-xs tracking-wider uppercase">{t('profit_factor')}</span>
                <Percent className="w-5 h-5 text-zinc-500" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-baseline space-x-1">
                  <span className={`text-4xl font-extrabold tracking-tight ${kpi.profit_factor >= 1.5 ? 'text-indigo-400' : 'text-slate-200'}`}>
                    {kpi.profit_factor === 999.0 ? '∞' : kpi.profit_factor}
                  </span>
                </div>
                <span className="text-zinc-500 text-xs font-semibold mt-1">
                  {kpi.profit_factor >= 2.0 ? t('profit_factor_excellent') : kpi.profit_factor >= 1.0 ? t('profit_factor_good') : t('profit_factor_poor')}
                </span>
              </div>
            </div>
          </div>

          {/* Total Trades */}
          <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl hover:border-zinc-700 transition-colors duration-300">
            <div className="flex flex-col justify-between h-full space-y-4">
              <div className="flex items-center justify-between text-zinc-400">
                <span className="font-bold text-xs tracking-wider uppercase">{t('total_trades')}</span>
                <Activity className="w-5 h-5 text-zinc-500" />
              </div>
              <div className="flex flex-col gap-1">
                <div className="flex items-baseline space-x-1">
                  <span className="text-4xl font-extrabold tracking-tight text-white">
                    {kpi.total_trades}
                  </span>
                </div>
                <span className="text-zinc-500 text-xs font-semibold mt-1">
                  {t('total_trades_desc')}
                </span>
              </div>
            </div>
          </div>

        </div>

        {/* Main Cumulative PnL Chart */}
        <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 md:p-8 shadow-xl">
          <h2 className="text-xl font-bold text-white mb-6 flex items-center space-x-2">
            <TrendingUp className="w-5 h-5 text-zinc-400" />
            <span>{t('cumulative_profit')}</span>
          </h2>
          <div className="h-96 min-h-96 w-full min-w-0 overflow-hidden">
            {chart_data.length > 0 ? (
              <ResponsiveContainer width="100%" height={384} minWidth={0} minHeight={240}>
                <AreaChart data={chart_data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorPnL" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={isProfitable ? chartColors.profit : chartColors.loss} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={isProfitable ? chartColors.profit : chartColors.loss} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis
                    dataKey="date"
                    stroke="#71717a"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickMargin={12}
                  />
                  <YAxis
                    stroke="#71717a"
                    fontSize={12}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => `$${val}`}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'var(--surface-card)', border: '1px solid var(--border-subtle)', borderRadius: '16px', color: '#fff', boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.7)' }}
                    itemStyle={{ color: '#fff', fontWeight: 'bold' }}
                    labelStyle={{ color: '#a1a1aa', marginBottom: '8px' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="cumulative_pnl"
                    name={t('cumulative_profit_series')}
                    stroke={isProfitable ? chartColors.profit : chartColors.loss}
                    strokeWidth={3}
                    fillOpacity={1}
                    fill="url(#colorPnL)"
                    animationDuration={1200}
                    animationEasing="ease-out"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-zinc-500">
                <Activity className="w-12 h-12 mb-4 opacity-50" />
                <p>{t('no_trades')}</p>
              </div>
            )}
          </div>
        </div>

        {/* 실시간 체결 로그 팝업 메뉴 버튼 */}
        <div className="flex justify-center pt-4 pb-8">
          <Button
            variant="secondary"
            size="lg"
            onClick={() => setIsLogsModalOpen(true)}
            leftIcon={<Activity className="w-4 h-4 text-zinc-400" />}
          >
            {t('view_all_logs')}
          </Button>
        </div>

        {/* 전체 거래 내역 모달 */}
        <Modal
          isOpen={isLogsModalOpen}
          onClose={() => setIsLogsModalOpen(false)}
          maxWidth="5xl"
        >
          <TradeLogs logs={logs} isModalMode={true} />
        </Modal>

      </div>
    </div>
  );
}

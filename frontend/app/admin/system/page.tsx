"use client";

import React, { useState } from 'react';
import { useSystemHealth } from '../../../hooks/useSystemHealth';
import { Server, Database, Bot, RefreshCw, HardDrive, Cpu, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react';

const StatusBadge = ({ status }: { status: string }) => {
  if (status === 'connected') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
        Healthy
      </span>
    );
  }
  // 미구현 상태: 실제 핑을 하지 않으므로 정상/장애 어느 쪽으로도 단정하지 않고 중립 표기
  if (status === 'not_implemented') {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">
        <span className="w-2 h-2 rounded-full bg-zinc-500"></span>
        N/A
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
      <span className="w-2 h-2 rounded-full bg-rose-500"></span>
      Degraded
    </span>
  );
};

const MetricCard = ({ 
  title, 
  value, 
  subtitle, 
  icon: Icon,
  warning = false
}: { 
  title: string, 
  value: React.ReactNode, 
  subtitle?: string,
  icon: React.ElementType,
  warning?: boolean
}) => (
  <div className="relative group overflow-hidden rounded-2xl bg-[#1C1F26]/60 backdrop-blur-xl border border-white/5 p-6 hover:border-white/10 transition-all duration-300">
    <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
    <div className="flex justify-between items-start mb-4">
      <div className="p-3 bg-white/5 rounded-xl border border-white/5">
        <Icon className={`w-6 h-6 ${warning ? 'text-amber-400' : 'text-blue-400'}`} />
      </div>
    </div>
    <h3 className="text-sm font-medium text-gray-400 mb-1">{title}</h3>
    <div className="flex items-baseline gap-2">
      <span className={`text-2xl font-bold tracking-tight ${warning ? 'text-amber-400' : 'text-white'}`}>
        {value}
      </span>
      {subtitle && <span className="text-sm text-gray-500">{subtitle}</span>}
    </div>
  </div>
);

export default function SystemHealthPage() {
  const [refreshInterval, setRefreshInterval] = useState<number>(0); // 0 means manual only
  const { core, bot, brokers, loadingCore, loadingBot, loadingBrokers, refetch } = useSystemHealth(refreshInterval);

  return (
    <div className="min-h-screen bg-[#0A0D14] text-white selection:bg-blue-500/30 selection:text-blue-200">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pt-24 space-y-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              System Health
            </h1>
            <p className="text-gray-400 mt-2 text-sm">
              Real-time infrastructure and broker integration monitoring
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              className="bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-gray-300 focus:outline-none focus:border-white/20 transition-colors"
            >
              <option value={0} className="bg-zinc-900">Auto-refresh: OFF</option>
              <option value={10000} className="bg-zinc-900">Every 10s</option>
              <option value={30000} className="bg-zinc-900">Every 30s</option>
              <option value={60000} className="bg-zinc-900">Every 1m</option>
            </select>
            <button
              onClick={refetch}
              className="group flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 transition-all text-sm font-medium"
            >
            <RefreshCw className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
            Refresh
          </button>
        </div>
        </div>

        {/* Section 1: Core Infrastructure */}
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b border-white/10 pb-2">
            <Server className="w-5 h-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-200">Core Infrastructure</h2>
            {loadingCore && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin ml-2" />}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard 
              title="Redis Cache" 
              value={core?.redis ? <StatusBadge status={core.redis.status} /> : '...'} 
              subtitle={core ? `${core.redis.latency_ms}ms ping` : ''}
              icon={Database} 
            />
            <MetricCard 
              title="Database Pool" 
              value={core?.database ? <StatusBadge status={core.database.status} /> : '...'} 
              subtitle={core ? `${core.database.type} (${core.database.latency_ms}ms)` : ''}
              icon={Database} 
            />
            <MetricCard 
              title="Memory Usage" 
              value={core ? `${core.resources.memory_usage_percent}%` : '...'} 
              warning={core?.resources.memory_warning}
              icon={Cpu} 
            />
            <MetricCard 
              title="Disk Space" 
              value={core ? `${core.resources.disk_usage_percent}%` : '...'} 
              warning={core?.resources.disk_warning}
              icon={HardDrive} 
            />
          </div>
        </div>

        {/* Section 2: Trading Bot */}
        <div className="space-y-4 pt-4">
          <div className="flex items-center gap-2 border-b border-white/10 pb-2">
            <Bot className="w-5 h-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-200">Bot Scheduler</h2>
            {loadingBot && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin ml-2" />}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center justify-between p-5 rounded-2xl bg-[#1C1F26]/60 border border-white/5">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-white/5 rounded-xl">
                  <Bot className="w-6 h-6 text-indigo-400" />
                </div>
                <div>
                  <h3 className="font-medium text-gray-200">Main Loop Status</h3>
                  <p className="text-sm text-gray-500 mt-1">Background Trading Engine</p>
                </div>
              </div>
              <div className="text-right">
                {bot?.scheduler.is_running ? (
                  <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                    <CheckCircle2 className="w-5 h-5" /> Active
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-rose-400 font-semibold">
                    <XCircle className="w-5 h-5" /> Halted
                  </div>
                )}
                <div className="text-sm text-gray-500 mt-1">{bot?.scheduler.jobs_count || 0} active jobs</div>
              </div>
            </div>

            <div className="flex items-center justify-between p-5 rounded-2xl bg-[#1C1F26]/60 border border-white/5">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-white/5 rounded-xl">
                  <RefreshCw className={`w-6 h-6 text-purple-400 ${bot?.trading_loop.is_processing ? 'animate-spin' : ''}`} />
                </div>
                <div>
                  <h3 className="font-medium text-gray-200">Cycle Execution</h3>
                  <p className="text-sm text-gray-500 mt-1">Is currently evaluating markets?</p>
                </div>
              </div>
              <div className="text-right">
                <span className={`text-lg font-semibold ${bot?.trading_loop.is_processing ? 'text-purple-400' : 'text-gray-400'}`}>
                  {bot?.trading_loop.is_processing ? 'Processing...' : 'Idle'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 3: Broker APIs */}
        <div className="space-y-4 pt-4">
          <div className="flex items-center gap-2 border-b border-white/10 pb-2">
            <ShieldAlert className="w-5 h-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-200">Broker Integrations</h2>
            {loadingBrokers && <RefreshCw className="w-4 h-4 text-gray-500 animate-spin ml-2" />}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <MetricCard 
              title="Korea Investment (KIS)" 
              value={brokers?.kis ? <StatusBadge status={brokers.kis.status} /> : '...'}
              subtitle={brokers ? (brokers.kis.latency_ms != null ? `${brokers.kis.latency_ms}ms API ping` : '미구현 (ping 미측정)') : ''}
              warning={brokers?.kis.rate_limit_warning}
              icon={Server} 
            />
            <MetricCard 
              title="Toss Securities" 
              value={brokers?.toss ? <StatusBadge status={brokers.toss.status} /> : '...'}
              subtitle={brokers ? (brokers.toss.latency_ms != null ? `${brokers.toss.latency_ms}ms API ping` : '미구현 (ping 미측정)') : ''}
              warning={brokers?.toss.rate_limit_warning}
              icon={Server} 
            />
          </div>
        </div>

      </main>
    </div>
  );
}

'use client';
import React, { useState, useEffect } from 'react';
import {
  Users,
  Loader2,
  Play,
  Square,
  Trash2,
  X,
  Calendar,
  Bot,
  Key,
  Send,
  Shield,
  Trophy,
  TrendingUp,
  TrendingDown,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  type TooltipValueType,
} from 'recharts';
import useSWR from 'swr';
import api, { fetcher } from '@/lib/api';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

// ... (기존 인터페이스들 유지)
interface BrokerCredentialMeta {
  broker_name: string;
  has_credentials: boolean;
  account_no_masked: string | null;
  verification_status: string;
  verified_trade_mode: string | null;
  verified_at: string | null;
  credential_error: string | null;
}

interface EquityPoint {
  timestamp: string;
  total: number;
}

interface ManagedUser {
  id: number;
  username: string;
  role: string;
  created_at: string;
  trade_mode: string;
  broker_provider: string;
  telegram_enabled: boolean;
  telegram_chat_id: string | null;
  is_running: boolean;
  profit_rate: number;
  strategy_type: string;
  strategy_name?: string;
  credentials: BrokerCredentialMeta[];
  equity_curve?: EquityPoint[];
}

export function UserManagement() {
  const { data: swrData, isLoading, mutate } = useSWR('/admin/users', fetcher, { refreshInterval: 15000 });
  const usersList: ManagedUser[] = Array.isArray(swrData) ? swrData : (swrData?.data || []);
  const loading = isLoading;

  const [actionUserId, setActionUserId] = useState<number | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const selectedUser = usersList.find(u => u.id === selectedUserId) || null;
  const [sortByProfit, setSortByProfit] = useState<boolean>(true); // 기본적으로 수익률 기준 정렬 활성화
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;

  // Esc key to close drawer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedUserId(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleToggleUserBot = async (userId: number) => {
    setActionUserId(userId);
    try {
      const res = await api.post(`/admin/users/${userId}/toggle-bot`);
      toast.success(res.data.is_running ? "봇이 성공적으로 가동되었습니다." : "봇이 일시정지 되었습니다.");
      mutate();
    } catch (error) {
      toast.error(`봇 상태 변경에 실패했습니다: ${getErrorMessage(error)}`);
    } finally {
      setActionUserId(null);
    }
  };

  const handleDeleteUser = async (userId: number, username: string) => {
    if (!confirm(`🚨 경고: 정말로 [${username}] 사용자를 영구 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며, 모든 잔고 및 거래 내역이 삭제됩니다.`)) {
      return;
    }
    setActionUserId(userId);
    try {
      await api.post(`/admin/users/${userId}/delete`);
      toast.success(`[${username}] 계정이 안전하게 영구 삭제되었습니다.`);
      setSelectedUserId(null); // Close drawer on success
      mutate();
    } catch (error) {
      toast.error(`사용자 삭제에 실패했습니다: ${getErrorMessage(error)}`);
    } finally {
      setActionUserId(null);
    }
  };

  // Recharts를 위한 모든 경쟁 사용자의 자산 성장 곡선 병합 데이터 산출
  const getChartData = () => {
    if (!Array.isArray(usersList) || usersList.length === 0) return [];

    // 타임스탬프 기준의 모든 지점들을 정렬하여 유니크 타임라인 확보
    const timelineSet = new Set<string>();
    usersList.forEach(u => {
      if (u.equity_curve) {
        u.equity_curve.forEach((point: EquityPoint) => {
          timelineSet.add(point.timestamp);
        });
      }
    });

    const sortedTimeline = Array.from(timelineSet).sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

    return sortedTimeline.map(ts => {
      // 차트 가독성을 위해 'HH:MM:SS' 또는 'MM-DD HH:MM' 형태로 시간 포맷팅
      let formattedTime = ts;
      try {
        const d = new Date(ts);
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const date = String(d.getDate()).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        formattedTime = `${month}-${date} ${hours}:${minutes}`;
      } catch {
        formattedTime = ts.split(' ')[1] || ts;
      }

      const chartItem: Record<string, string | number> = { timestamp: formattedTime };

      usersList.forEach(u => {
        if (!u.equity_curve || u.equity_curve.length === 0) return;
        // 해당 타임스탬프 이하의 가장 최근 평가액을 매핑
        let lastVal: number | undefined;
        for (let i = 0; i < u.equity_curve.length; i++) {
          if (new Date(u.equity_curve[i].timestamp).getTime() <= new Date(ts).getTime()) {
            lastVal = u.equity_curve[i].total;
          } else {
            break;
          }
        }
        if (lastVal !== undefined) {
          chartItem[`user_${u.id}`] = Math.round(lastVal);
        }
      });
      return chartItem;
    });
  };

  const getLineColor = (index: number) => {
    const colors = [
      '#3b82f6', // 1: Blue
      '#f59e0b', // 2: Gold
      '#10b981', // 3: Emerald
      '#ec4899', // 4: Pink
      '#8b5cf6', // 5: Purple
      '#06b6d4', // 6: Cyan
      '#f43f5e', // 7: Rose
    ];
    return colors[index % colors.length];
  };

  const getRankBadge = (rank: number) => {
    switch (rank) {
      case 1:
        return (
          <span className="w-5 h-5 rounded-full bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 text-slate-950 font-bold flex items-center justify-center text-[10px] shadow-md shadow-amber-500/20">
            1
          </span>
        );
      case 2:
        return (
          <span className="w-5 h-5 rounded-full bg-gradient-to-br from-slate-200 via-zinc-400 to-zinc-600 text-slate-950 font-bold flex items-center justify-center text-[10px] shadow-md shadow-slate-500/10">
            2
          </span>
        );
      case 3:
        return (
          <span className="w-5 h-5 rounded-full bg-gradient-to-br from-amber-600 via-amber-700 to-amber-900 text-slate-100 font-bold flex items-center justify-center text-[10px]">
            3
          </span>
        );
      default:
        return (
          <span className="w-5 h-5 rounded-full bg-zinc-800 text-zinc-400 font-bold flex items-center justify-center text-[10px] border border-zinc-700/50">
            {rank}
          </span>
        );
    }
  };

  const getReturnBadge = (rate: number | string | null | undefined) => {
    if (rate === null || rate === undefined) {
      return <span className="text-zinc-600 text-xs">-</span>;
    }
    const numRate = Number(rate);
    if (isNaN(numRate)) {
      return <span className="text-zinc-600 text-xs">-</span>;
    }
    const isPositive = numRate > 0;
    const isNegative = numRate < 0;
    return (
      <span className={`px-2 py-1 rounded text-[15px] font-semibold font-mono flex items-center gap-1 w-fit border
        ${isPositive
          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
          : isNegative
            ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
            : 'bg-zinc-800 text-zinc-500 border-zinc-750'}`}>
        {isPositive ? <TrendingUp size={15} /> : isNegative ? <TrendingDown size={15} /> : null}
        {numRate > 0 ? '+' : ''}{numRate.toFixed(2)}%
      </span>
    );
  };

  const formatTooltipValue = (value: TooltipValueType | undefined) => {
    const numericValue = Array.isArray(value) ? value[0] : value;
    return [`${Number(numericValue ?? 0).toLocaleString()}원`, ''];
  };

  // 정렬 규칙 적용된 유저 목록
  const sortedUsers = Array.isArray(usersList) ? [...usersList].sort((a, b) => {
    if (sortByProfit) {
      const aRate = Number(a.profit_rate) || 0;
      const bRate = Number(b.profit_rate) || 0;
      return bRate - aRate;
    }
    return a.id - b.id;
  }) : [];

  const totalPages = Math.ceil(sortedUsers.length / itemsPerPage);
  const paginatedUsers = sortedUsers.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const chartData = getChartData();
  const chartUsers = usersList.filter(
    user => user.equity_curve && user.equity_curve.length > 0
  );

  return (
    <div className="space-y-6">
      {/* 상단 랭킹 종합 차트 보드 */}
      {!loading && usersList.length > 0 && chartData.length > 0 && (
        <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Trophy size={16} className="text-amber-400" />
              실시간 아레나 리그 자산 성장 추이
            </h3>
            <span className="text-[10px] text-zinc-500 font-bold uppercase tracking-wider">
              REAL-TIME EQUITY CURVE COMPARISON
            </span>
          </div>

          <div className="h-[240px] min-h-[240px] w-full min-w-0 overflow-hidden text-slate-400">
            <ResponsiveContainer width="100%" height={240} minWidth={0} minHeight={180}>
              <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b/20" vertical={false} />
                <XAxis
                  dataKey="timestamp"
                  stroke="#475569"
                  fontSize={9}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="#475569"
                  fontSize={9}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${(v / 10000).toLocaleString()}만`}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#090d16', border: '1px solid #334155', borderRadius: '12px', fontSize: '10px', color: '#cbd5e1' }}
                  formatter={formatTooltipValue}
                />
                <Legend
                  verticalAlign="top"
                  height={28}
                  iconType="circle"
                  iconSize={6}
                  wrapperStyle={{ fontSize: '10px', fontWeight: 'bold' }}
                />
                {chartUsers.map((user, idx) => (
                  <Line
                    key={user.username}
                    type="monotone"
                    dataKey={`user_${user.id}`}
                    name={user.username}
                    stroke={getLineColor(idx)}
                    strokeWidth={user.username === 'admin' ? 2 : 1.5}
                    dot={false}
                    activeDot={{ r: 3 }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 사용자 관리 테이블 보드 */}
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Users size={18} className="text-blue-400" />
            사용자 관리 & 실시간 아레나
          </h2>
          <div className="flex items-center gap-3">
            {/* 랭킹 정렬 토글 스위치 */}
            <button
              onClick={() => {
                setSortByProfit(!sortByProfit);
                setCurrentPage(1);
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all duration-200 cursor-pointer ${
                sortByProfit
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  : 'bg-zinc-800/50 text-zinc-400 border-zinc-700/50'
              }`}
            >
              <Trophy size={13} className={sortByProfit ? 'text-amber-400 animate-pulse' : 'text-zinc-500'} />
              수익률 랭킹순
            </button>
            <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
              TOTAL: {usersList.length} USERS
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3">
              <Loader2 size={36} className="animate-spin text-zinc-500" />
              <span className="text-xs text-zinc-500 font-semibold">사용자 데이터 로딩 중...</span>
            </div>
          ) : usersList.length === 0 ? (
            <div className="py-16 text-center">
              <Users size={48} className="mx-auto text-zinc-700 mb-3" />
              <p className="text-sm font-semibold text-zinc-500">가입된 사용자가 없습니다.</p>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-zinc-800/60">
              <thead>
                <tr className="text-left text-xs uppercase text-zinc-500 font-bold tracking-wider">
                  <th className="px-6 py-3.5 text-center w-12">순위</th>
                  <th className="px-6 py-3.5">사용자명</th>
                  <th className="px-6 py-3.5">투자 모드</th>
                  <th className="px-6 py-3.5">연동 전략</th>
                  <th className="px-6 py-3.5">텔레그램</th>
                  <th className="px-6 py-3.5">봇 상태</th>
                  <th className="px-6 py-3.5">실시간 수익률</th>
                  <th className="px-6 py-3.5 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40 text-[15px]">
                {paginatedUsers.map((user, index) => {
                  const rank = (currentPage - 1) * itemsPerPage + index + 1;
                  return (
                    <tr
                      key={user.id}
                      onClick={() => setSelectedUserId(user.id)}
                      className={`transition-colors duration-150 cursor-pointer hover:bg-zinc-800/20 ${selectedUser?.id === user.id ? 'bg-zinc-800/35' : ''}`}
                    >
                      <td className="px-6 py-4 text-center">
                        <div className="flex justify-center">
                          {sortByProfit ? getRankBadge(rank) : (
                            <span className="text-xs font-mono text-zinc-500 font-bold">{user.id}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-bold text-slate-300">
                        <div className="flex items-center gap-2">
                          {user.username}
                          {user.role === 'ADMIN' && (
                            <span className="text-[9px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-1.5 py-0.5 rounded font-black">
                              ADMIN
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[10px] font-bold border ${
                          user.trade_mode === 'REAL' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                          user.trade_mode === 'MOCK' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                          'bg-blue-500/10 text-blue-400 border-blue-500/20'
                        }`}>
                          {user.trade_mode}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-slate-400 font-semibold text-xs">
                        {user.strategy_name || user.strategy_type?.replace(/_/g, ' ')}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[10px] font-bold ${
                          user.telegram_enabled ? 'bg-indigo-500/10 text-indigo-400' : 'bg-zinc-800 text-zinc-500'
                        }`}>
                          {user.telegram_enabled ? 'ON' : 'OFF'}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${user.is_running ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`}></span>
                          <span className={`text-[10px] font-bold ${user.is_running ? 'text-emerald-400' : 'text-zinc-500'}`}>
                            {user.is_running ? 'RUNNING' : 'STOPPED'}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 font-mono">
                        {getReturnBadge(user.profit_rate)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleToggleUserBot(user.id); }}
                            disabled={actionUserId === user.id}
                            className={`p-1.5 rounded-lg transition-colors cursor-pointer border ${
                              user.is_running
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
                            }`}
                            title={user.is_running ? "봇 정지" : "봇 가동"}
                          >
                            {actionUserId === user.id ? <Loader2 size={16} className="animate-spin" /> : user.is_running ? <Square size={16} /> : <Play size={16} />}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteUser(user.id, user.username); }}
                            disabled={actionUserId === user.id || user.username === 'admin'}
                            className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                            title="계정 영구 삭제"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination Controls */}
        {!loading && sortedUsers.length > 0 && totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-zinc-800/60 pt-4 px-2">
            <span className="text-xs text-zinc-500 font-semibold">
              총 {sortedUsers.length}명 중 {(currentPage - 1) * itemsPerPage + 1}-
              {Math.min(currentPage * itemsPerPage, sortedUsers.length)}명 표시
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-1.5 rounded-lg border border-zinc-700/50 text-zinc-400 hover:bg-zinc-800 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={16} />
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`w-7 h-7 flex items-center justify-center rounded-lg text-xs font-bold transition-colors ${
                      currentPage === page
                        ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                        : 'text-zinc-500 hover:bg-zinc-800 hover:text-slate-300'
                    }`}
                  >
                    {page}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="p-1.5 rounded-lg border border-zinc-700/50 text-zinc-400 hover:bg-zinc-800 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      <AnimatePresence>
        {selectedUser && (
          <>
            {/* Backdrop Overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedUserId(null)}
              className="absolute inset-0 bg-black/60 backdrop-blur-sm z-40"
            />

            {/* Slide-over Drawer Panel */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed top-0 right-0 h-full w-full max-w-md bg-[#0f1424] border-l border-zinc-800/80 shadow-2xl z-50 overflow-y-auto flex flex-col"
            >
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-zinc-800/80 bg-[#0c0f1c]/50">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 bg-blue-500/10 rounded-xl">
                    <Users size={20} className="text-blue-400" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-slate-100 font-sans">사용자 상세 프로필</h3>
                    <p className="text-[10px] text-zinc-500 font-mono">ID: {selectedUser?.id}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedUserId(null)}
                  className="w-8 h-8 rounded-full bg-zinc-800/50 hover:bg-zinc-700/80 flex items-center justify-center text-zinc-400 hover:text-white transition-all active:scale-90"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Body */}
              <div className="p-6 space-y-6 flex-1">
                {/* User Header Info Card */}
                <div className="bg-[#0b0e1a]/40 border border-zinc-800/40 rounded-2xl p-4 flex items-center justify-between">
                  <div className="space-y-1">
                    <div className="text-xs text-zinc-500 font-semibold">사용자명</div>
                    <div className="text-lg font-bold text-slate-200">{selectedUser.username}</div>
                  </div>
                  <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold flex items-center gap-1 ${
                    selectedUser.role === 'ADMIN'
                      ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                      : 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                  }`}>
                    <Shield size={10} />
                    {selectedUser.role}
                  </span>
                </div>

                {/* Section 1: 계정 및 가입 정보 */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Calendar size={14} className="text-zinc-500" />
                    계정 및 가입 정보
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">가입 일시</span>
                      <span className="text-slate-300 font-mono text-xs font-semibold">
                        {selectedUser.created_at ? new Date(selectedUser.created_at).toLocaleString('ko-KR', {
                          year: 'numeric',
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit'
                        }) : '-'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Section 2: 봇 및 전략 설정 */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Bot size={14} className="text-zinc-500" />
                    자동매매 및 전략 설정
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">현재 투자 모드</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.trade_mode === 'REAL' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                        selectedUser.trade_mode === 'MOCK' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                        {selectedUser.trade_mode}
                      </span>
                    </div>
                    <div className="flex justify-between items-center font-sans">
                      <span className="text-zinc-500 text-xs font-semibold">실시간 봇 수익률</span>
                      {getReturnBadge(selectedUser.profit_rate)}
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">구동 알고리즘 전략</span>
                      <span className="text-slate-300 font-bold bg-zinc-800/50 px-2 py-0.5 rounded text-[10px] border border-zinc-700/50">
                        {selectedUser.strategy_name || selectedUser.strategy_type?.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">주요 증권사</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.trade_mode === 'SIMULATED'
                          ? 'bg-zinc-800 text-zinc-500 border border-zinc-700/30'
                          : 'text-slate-300 bg-zinc-800/50 border border-zinc-700/50'
                      }`}>
                        {selectedUser.trade_mode === 'SIMULATED' ? '없음 (가상 시뮬레이터)' : selectedUser.broker_provider}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Section 3: 증권사 연동 계좌 정보 */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Key size={14} className="text-zinc-500" />
                    증권사 API 연동 내역
                  </h4>
                  <div className="space-y-2">
                    {!selectedUser.credentials || selectedUser.credentials.length === 0 ? (
                      <div className="bg-[#0b0e1a]/10 border border-zinc-800/30 rounded-2xl p-4 text-center text-xs text-zinc-500 font-semibold">
                        연동된 증권사 API 정보가 없습니다.
                      </div>
                    ) : (
                      selectedUser.credentials.map((cred, idx) => (
                        <div key={idx} className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-2 text-sm">
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-slate-350 text-xs">{cred.broker_name}</span>
                            <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${
                              cred.verification_status === 'verified' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                              cred.verification_status === 'failed' ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                              cred.verification_status === 'crypto_error' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                              'bg-zinc-800 text-zinc-500'
                            }`}>
                              {cred.verification_status.toUpperCase()}
                            </span>
                          </div>
                          <div className="flex justify-between items-center text-xs">
                            <span className="text-zinc-500 font-semibold">마스킹된 계좌번호</span>
                            <span className="font-mono text-slate-300 font-bold">{cred.account_no_masked || '미등록'}</span>
                          </div>
                          {cred.verified_at && (
                            <div className="flex justify-between items-center text-[10px] text-zinc-500">
                              <span>마지막 검증</span>
                              <span className="font-mono">
                                {new Date(cred.verified_at).toLocaleDateString('ko-KR')}
                              </span>
                            </div>
                          )}
                          {cred.credential_error && (
                            <div className="text-[10px] text-rose-400 bg-rose-500/5 p-2 rounded-lg border border-rose-500/10">
                              {cred.credential_error}
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* Section 4: 텔레그램 알림 설정 */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Send size={14} className="text-zinc-500" />
                    텔레그램 알림 정보
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">알림 상태</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.telegram_enabled ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-zinc-800 text-zinc-500'
                      }`}>
                        {selectedUser.telegram_enabled ? '활성화 (ON)' : '비활성화 (OFF)'}
                      </span>
                    </div>
                    {selectedUser.telegram_enabled && (
                      <div className="flex justify-between items-center text-xs">
                        <span className="text-zinc-500 font-semibold">채팅방 ID</span>
                        <span className="font-mono text-slate-300 font-bold">{selectedUser.telegram_chat_id || '미설정'}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Footer Actions */}
              <div className="p-6 border-t border-zinc-800/80 bg-[#0c0f1c]/30 flex gap-3">
                <button
                  onClick={() => handleToggleUserBot(selectedUser.id)}
                  disabled={actionUserId === selectedUser.id}
                  className={`flex-1 py-2.5 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-205 cursor-pointer border ${
                    selectedUser.is_running
                      ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                      : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20'
                  }`}
                >
                  {actionUserId === selectedUser.id ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : selectedUser.is_running ? (
                    <>
                      <Square size={16} /> 봇 일시 정지
                    </>
                  ) : (
                    <>
                      <Play size={16} /> 봇 거래 기동
                    </>
                  )}
                </button>

                <button
                  onClick={() => handleDeleteUser(selectedUser.id, selectedUser.username)}
                  disabled={actionUserId === selectedUser.id || selectedUser.username === 'admin'}
                  className="px-4 py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed text-xs font-bold transition-all duration-200 cursor-pointer"
                  title="계정 영구 삭제"
                >
                  <Trash2 size={16} />
                </button>
              </div>

            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

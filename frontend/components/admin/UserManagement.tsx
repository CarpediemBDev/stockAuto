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
  ChevronRight,
  Search
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import useSWR from 'swr';
import { pollInterval } from '@/lib/sse';
import { useNow } from '@/hooks/useFreshness';
import { useSseConnection } from '@/providers/EventStreamProvider';
import { adminAPI, fetcher } from '@/lib/api';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';
import { useTranslations } from 'next-intl';

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
  latest_snapshot_at?: string | null;
}

export function UserManagement() {
  const { data: swrData, isLoading, mutate } = useSWR('/admin/users', fetcher, { refreshInterval: pollInterval(15000) });
  const usersList: ManagedUser[] = Array.isArray(swrData) ? swrData : (swrData?.data || []);
  const loading = isLoading;
  const t = useTranslations('admin.users');

  const [actionUserId, setActionUserId] = useState<number | null>(null);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);
  const selectedUser = usersList.find(u => u.id === selectedUserId) || null;
  const [sortByProfit, setSortByProfit] = useState<boolean>(true); // 기본적으로 수익률 기준 정렬 활성화
  const [tradeModeFilter, setTradeModeFilter] = useState<'ALL' | 'SIMULATED' | 'MOCK' | 'REAL'>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;

  // 스냅샷 신선도: 공유 클럭(useNow) + SSE 서버 오프셋(clock-skew 보정). 컴포넌트별 타이머 제거.
  const now = useNow();
  const { serverOffsetMs } = useSseConnection();

  // 최신 스냅샷 시각이 90초 이상 낡았는지 판정. 관리자도 낡음을 숨기지 않는다.
  const snapshotStaleness = (user: ManagedUser): { isStale: boolean; label: string } | null => {
    if (!user.latest_snapshot_at || now === 0) return null;
    const latestTs = new Date(user.latest_snapshot_at).getTime();
    if (Number.isNaN(latestTs)) return null;
    const ageSec = Math.floor((now + serverOffsetMs - latestTs) / 1000);
    if (ageSec < 90) return { isStale: false, label: "" };
    const label = ageSec >= 60
      ? t('staleness_min', { n: Math.floor(ageSec / 60) })
      : t('staleness_sec', { n: ageSec });
    return { isStale: true, label };
  };

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
      const res = await adminAPI.toggleUserBot(userId);
      toast.success(res.data.is_running ? t('toast_bot_started') : t('toast_bot_paused'));
      mutate();
    } catch (error) {
      toast.error(t('toast_bot_toggle_failed', { error: getErrorMessage(error) }));
    } finally {
      setActionUserId(null);
    }
  };

  const handleDeleteUser = (userId: number, username: string) => {
    toast(t('confirm_delete_title', { username }), {
      description: t('confirm_delete_desc'),
      action: {
        label: t('confirm_delete_action'),
        onClick: async () => {
          setActionUserId(userId);
          try {
            await adminAPI.deleteUser(userId);
            toast.success(t('toast_delete_success', { username }));
            setSelectedUserId(null); // Close drawer on success
            mutate();
          } catch (error) {
            toast.error(t('toast_delete_failed', { error: getErrorMessage(error) }));
          } finally {
            setActionUserId(null);
          }
        }
      },
      cancel: {
        label: t('confirm_cancel'),
        onClick: () => {}
      }
    });
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



  // 1. 거래모드 및 다차원 통합 검색(사용자명, 전략명, 증권사명) 필터링 적용
  const filteredUsers = Array.isArray(usersList)
    ? usersList.filter(u => {
        const matchesMode = tradeModeFilter === 'ALL' || u.trade_mode === tradeModeFilter;
        if (!matchesMode) return false;

        if (!searchQuery.trim()) return true;
        const q = searchQuery.toLowerCase().trim();
        const matchUsername = u.username?.toLowerCase().includes(q);
        const matchStrategy = (u.strategy_name || u.strategy_type)?.toLowerCase().includes(q);
        const matchBroker = u.broker_provider?.toLowerCase().includes(q);

        return matchUsername || matchStrategy || matchBroker;
      })
    : [];

  // 2. 정렬 규칙 적용된 유저 목록 (선택된 거래모드 내 랭킹 정렬)
  const sortedUsers = [...filteredUsers].sort((a, b) => {
    if (sortByProfit) {
      const aRate = Number(a.profit_rate) || 0;
      const bRate = Number(b.profit_rate) || 0;
      return bRate - aRate;
    }
    return a.id - b.id;
  });

  const totalPages = Math.ceil(sortedUsers.length / itemsPerPage);
  const paginatedUsers = sortedUsers.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);



  return (
    <div className="space-y-6">


      {/* 사용자 관리 테이블 보드 */}
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-4 md:p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-zinc-800 pb-3 gap-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Users size={18} className="text-blue-400" />
            {t('title')}
          </h2>
          <div className="flex flex-wrap items-center gap-3">
            {/* 실시간 통합 검색 바 */}
            <div className="relative flex items-center min-w-[180px] max-w-[240px]">
              <Search size={14} className="absolute left-2.5 text-zinc-500 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder={t('search_placeholder')}
                className="w-full bg-zinc-900/90 border border-zinc-800 focus:border-blue-500/50 text-slate-200 text-xs rounded-lg pl-8 pr-7 py-1.5 outline-none transition-colors placeholder:text-zinc-500 font-sans"
              />
              {searchQuery && (
                <button
                  onClick={() => {
                    setSearchQuery('');
                    setCurrentPage(1);
                  }}
                  className="absolute right-2 text-zinc-500 hover:text-zinc-300 p-0.5 rounded cursor-pointer"
                  title={t('search_clear')}
                >
                  <X size={12} />
                </button>
              )}
            </div>

            {/* 거래모드 필터 탭 */}
            <div className="flex items-center bg-zinc-900/80 p-0.5 rounded-lg border border-zinc-800 text-xs">
              {(['ALL', 'SIMULATED', 'MOCK', 'REAL'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => {
                    setTradeModeFilter(mode);
                    setCurrentPage(1);
                  }}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-colors cursor-pointer ${
                    tradeModeFilter === mode
                      ? mode === 'REAL' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                        mode === 'MOCK' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' :
                        mode === 'SIMULATED' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' :
                        'bg-zinc-700 text-slate-100'
                      : 'text-zinc-400 hover:text-slate-200'
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>

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
              {t('sort_profit')}
            </button>
            <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
              TOTAL: {filteredUsers.length} USERS
            </span>
          </div>
        </div>

        <div className="w-full overflow-x-auto">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3">
              <Loader2 size={36} className="animate-spin text-zinc-500" />
              <span className="text-xs text-zinc-500 font-semibold">{t('loading')}</span>
            </div>
          ) : usersList.length === 0 ? (
            <div className="py-16 text-center">
              <Users size={48} className="mx-auto text-zinc-700 mb-3" />
              <p className="text-sm font-semibold text-zinc-500">{t('no_data')}</p>
            </div>
          ) : (
            <table className="w-full divide-y divide-zinc-800/60">
              <thead>
                <tr className="text-left text-xs uppercase text-zinc-500 font-bold tracking-wider whitespace-nowrap">
                  <th className="px-2 md:px-3 py-3 text-center w-10">{t('col_rank')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_username')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_trade_mode')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_strategy')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_telegram')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_bot_status')}</th>
                  <th className="px-2 md:px-3 py-3">{t('col_return')}</th>
                  <th className="px-2 md:px-3 py-3 text-right">{t('col_manage')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40 text-[15px] whitespace-nowrap">
                {paginatedUsers.map((user, index) => {
                  const rank = (currentPage - 1) * itemsPerPage + index + 1;
                  return (
                    <tr
                      key={user.id}
                      onClick={() => setSelectedUserId(user.id)}
                      className={`transition-colors duration-150 cursor-pointer hover:bg-zinc-800/20 ${selectedUser?.id === user.id ? 'bg-zinc-800/35' : ''}`}
                    >
                      <td className="px-2 md:px-3 py-3 text-center">
                        <div className="flex justify-center">
                          {sortByProfit ? getRankBadge(rank) : (
                            <span className="text-xs font-mono text-zinc-500 font-bold">{user.id}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-2 md:px-3 py-3 font-bold text-slate-300">
                        <div className="flex items-center gap-2">
                          {user.username}
                          {user.role === 'ADMIN' && (
                            <span className="text-[9px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-1.5 py-0.5 rounded font-black">
                              ADMIN
                            </span>
                          )}
                          {user.username.toLowerCase().startsWith('obs_') && (
                            <span className="text-[9px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1.5 py-0.5 rounded font-black">
                              EXEMPT
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-2 md:px-3 py-3">
                        <span className={`px-2 py-1 rounded text-[10px] font-bold border ${
                          user.trade_mode === 'REAL' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                          user.trade_mode === 'MOCK' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                          'bg-blue-500/10 text-blue-400 border-blue-500/20'
                        }`}>
                          {user.trade_mode}
                        </span>
                      </td>
                      <td
                        className="px-2 md:px-3 py-3 text-slate-400 font-semibold text-xs max-w-[140px] truncate"
                        title={user.strategy_name || user.strategy_type?.replace(/_/g, ' ')}
                      >
                        {user.strategy_name || user.strategy_type?.replace(/_/g, ' ')}
                      </td>
                      <td className="px-2 md:px-3 py-3">
                        <span className={`px-2 py-1 rounded text-[10px] font-bold ${
                          user.telegram_enabled ? 'bg-indigo-500/10 text-indigo-400' : 'bg-zinc-800 text-zinc-500'
                        }`}>
                          {user.telegram_enabled ? 'ON' : 'OFF'}
                        </span>
                      </td>
                      <td className="px-2 md:px-3 py-3">
                        <div className="flex items-center gap-1.5">
                          <span className={`w-2 h-2 rounded-full ${user.is_running ? 'bg-emerald-500 animate-pulse' : 'bg-zinc-600'}`}></span>
                          <span className={`text-[10px] font-bold ${user.is_running ? 'text-emerald-400' : 'text-zinc-500'}`}>
                            {user.is_running ? 'RUNNING' : 'STOPPED'}
                          </span>
                        </div>
                      </td>
                      <td className="px-2 md:px-3 py-3 font-mono">
                        <div className="flex flex-col items-start gap-1">
                          {getReturnBadge(user.profit_rate)}
                          {(() => {
                            const stale = snapshotStaleness(user);
                            return stale?.isStale ? (
                              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded border tracking-wide bg-zinc-500/15 text-zinc-400 border-zinc-500/30 whitespace-nowrap">
                                ⚠️ {t('stale_basis', { label: stale.label })}
                              </span>
                            ) : null;
                          })()}
                        </div>
                      </td>
                      <td className="px-2 md:px-3 py-3">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleToggleUserBot(user.id); }}
                            disabled={actionUserId === user.id}
                            className={`p-1.5 rounded-lg transition-colors cursor-pointer border ${
                              user.is_running
                                ? 'bg-amber-500/10 text-amber-400 border-amber-500/20 hover:bg-amber-500/20'
                                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'
                            }`}
                            title={user.is_running ? t('title_bot_stop') : t('title_bot_start')}
                          >
                            {actionUserId === user.id ? <Loader2 size={16} className="animate-spin" /> : user.is_running ? <Square size={16} /> : <Play size={16} />}
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDeleteUser(user.id, user.username); }}
                            disabled={actionUserId === user.id || user.username === 'admin'}
                            className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20 hover:bg-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                            title={t('title_delete_account')}
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
              {t('pagination_summary', {
                total: sortedUsers.length,
                from: (currentPage - 1) * itemsPerPage + 1,
                to: Math.min(currentPage * itemsPerPage, sortedUsers.length),
              })}
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
                    <h3 className="text-base font-bold text-slate-100 font-sans">{t('detail_title')}</h3>
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
                    <div className="text-xs text-zinc-500 font-semibold">{t('col_username')}</div>
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
                    {t('section_account')}
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_signup_at')}</span>
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
                    {t('section_strategy')}
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_current_mode')}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.trade_mode === 'REAL' ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
                        selectedUser.trade_mode === 'MOCK' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                        'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                      }`}>
                        {selectedUser.trade_mode}
                      </span>
                    </div>
                    <div className="flex justify-between items-center font-sans">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_live_return')}</span>
                      {getReturnBadge(selectedUser.profit_rate)}
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_algo_strategy')}</span>
                      <span className="text-slate-300 font-bold bg-zinc-800/50 px-2 py-0.5 rounded text-[10px] border border-zinc-700/50">
                        {selectedUser.strategy_name || selectedUser.strategy_type?.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_broker')}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.trade_mode === 'SIMULATED'
                          ? 'bg-zinc-800 text-zinc-500 border border-zinc-700/30'
                          : 'text-slate-300 bg-zinc-800/50 border border-zinc-700/50'
                      }`}>
                        {selectedUser.trade_mode === 'SIMULATED' ? t('broker_none_sim') : selectedUser.broker_provider}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Section 3: 증권사 연동 계좌 정보 */}
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-zinc-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Key size={14} className="text-zinc-500" />
                    {t('section_broker_api')}
                  </h4>
                  <div className="space-y-2">
                    {!selectedUser.credentials || selectedUser.credentials.length === 0 ? (
                      <div className="bg-[#0b0e1a]/10 border border-zinc-800/30 rounded-2xl p-4 text-center text-xs text-zinc-500 font-semibold">
                        {t('no_broker_api')}
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
                            <span className="text-zinc-500 font-semibold">{t('field_masked_account')}</span>
                            <span className="font-mono text-slate-300 font-bold">{cred.account_no_masked || t('value_unregistered')}</span>
                          </div>
                          {cred.verified_at && (
                            <div className="flex justify-between items-center text-[10px] text-zinc-500">
                              <span>{t('field_last_verified')}</span>
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
                    {t('section_telegram')}
                  </h4>
                  <div className="bg-[#0b0e1a]/20 border border-zinc-800/50 rounded-2xl p-4 space-y-3.5 text-sm">
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">{t('field_notify_status')}</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.telegram_enabled ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20' : 'bg-zinc-800 text-zinc-500'
                      }`}>
                        {selectedUser.telegram_enabled ? t('value_enabled_on') : t('value_disabled_off')}
                      </span>
                    </div>
                    {selectedUser.telegram_enabled && (
                      <div className="flex justify-between items-center text-xs">
                        <span className="text-zinc-500 font-semibold">{t('field_chat_id')}</span>
                        <span className="font-mono text-slate-300 font-bold">{selectedUser.telegram_chat_id || t('value_unset')}</span>
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
                      <Square size={16} /> {t('btn_bot_pause')}
                    </>
                  ) : (
                    <>
                      <Play size={16} /> {t('btn_bot_start')}
                    </>
                  )}
                </button>

                <button
                  onClick={() => handleDeleteUser(selectedUser.id, selectedUser.username)}
                  disabled={actionUserId === selectedUser.id || selectedUser.username === 'admin'}
                  className="px-4 py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed text-xs font-bold transition-all duration-200 cursor-pointer"
                  title={t('title_delete_account')}
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

'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Users, Loader2, Play, Square, Trash2, X, Calendar, Bot, Key, Send, Shield } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import api from '@/lib/api';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

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
  is_real_enabled: boolean;
  strategy_type: string;
  credentials: BrokerCredentialMeta[];
}

export function UserManagement() {
  const [usersList, setUsersList] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionUserId, setActionUserId] = useState<number | null>(null);
  const [selectedUser, setSelectedUser] = useState<ManagedUser | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/admin/users");
      setUsersList(res.data);
      // Sync drawer data if open
      setSelectedUser((prev) => {
        if (!prev) return null;
        const updated = res.data.find((u: ManagedUser) => u.id === prev.id);
        return updated || null;
      });
    } catch (error) {
      toast.error(`사용자 목록을 불러오는 데 실패했습니다: ${getErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchUsers();
  }, [fetchUsers]);

  // Esc key to close drawer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedUser(null);
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
      fetchUsers();
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
      setSelectedUser(null); // Close drawer on success
      fetchUsers();
    } catch (error) {
      toast.error(`사용자 삭제에 실패했습니다: ${getErrorMessage(error)}`);
    } finally {
      setActionUserId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Users size={18} className="text-blue-400" />
            사용자 관리
          </h2>
          <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
            TOTAL: {usersList.length} USERS
          </span>
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
                  <th className="px-6 py-3.5">ID</th>
                  <th className="px-6 py-3.5">사용자명</th>
                  <th className="px-6 py-3.5">투자 모드</th>
                  <th className="px-6 py-3.5">텔레그램</th>
                  <th className="px-6 py-3.5">봇 상태</th>
                  <th className="px-6 py-3.5 text-right">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40 text-sm">
                {usersList.map((user) => (
                  <tr 
                    key={user.id} 
                    onClick={() => setSelectedUser(user)}
                    className={`transition-colors duration-150 cursor-pointer hover:bg-zinc-800/20 ${selectedUser?.id === user.id ? 'bg-zinc-800/35' : ''}`}
                  >
                    <td className="px-6 py-4 text-xs font-mono text-zinc-500 font-bold">{user.id}</td>
                    <td className="px-6 py-4 font-bold text-slate-300">{user.username}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[10px] font-bold ${
                        user.trade_mode === 'REAL' ? 'bg-red-500/10 text-red-400' :
                        user.trade_mode === 'MOCK' ? 'bg-amber-500/10 text-amber-400' :
                        'bg-blue-500/10 text-blue-400'
                      }`}>
                        {user.trade_mode}
                      </span>
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
                    <td className="px-6 py-4 text-right space-x-2">
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleToggleUserBot(user.id); }}
                        disabled={actionUserId === user.id}
                        className={`p-1.5 rounded-lg transition-colors ${
                          user.is_running 
                            ? 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20' 
                            : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                        }`}
                        title={user.is_running ? "봇 정지" : "봇 가동"}
                      >
                        {actionUserId === user.id ? <Loader2 size={16} className="animate-spin" /> : user.is_running ? <Square size={16} /> : <Play size={16} />}
                      </button>
                      <button 
                        onClick={(e) => { e.stopPropagation(); handleDeleteUser(user.id, user.username); }}
                        disabled={actionUserId === user.id || user.username === 'admin'}
                        className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        title="계정 영구 삭제"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <AnimatePresence>
        {selectedUser && (
          <>
            {/* Backdrop Overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedUser(null)}
              className="fixed inset-0 bg-black/60 backdrop-blur-xs z-40"
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
                    <p className="text-[10px] text-zinc-500 font-mono">ID: {selectedUser.id}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedUser(null)}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-slate-100 hover:bg-zinc-800/50 transition-all duration-200"
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
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">실전투자 허용 여부</span>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        selectedUser.is_real_enabled ? 'bg-red-500/15 text-red-400 border border-red-500/30' : 'bg-zinc-800 text-zinc-500'
                      }`}>
                        {selectedUser.is_real_enabled ? 'ENABLED' : 'DISABLED'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-zinc-500 text-xs font-semibold">구동 알고리즘 전략</span>
                      <span className="text-slate-300 font-bold bg-zinc-800/50 px-2 py-0.5 rounded text-[10px] border border-zinc-700/50 uppercase font-mono">
                        {selectedUser.strategy_type?.replace(/_/g, ' ')}
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
                  className={`flex-1 py-2.5 rounded-xl text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-205 cursor-pointer ${
                    selectedUser.is_running
                      ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20'
                      : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20'
                  }`}
                >
                  {actionUserId === selectedUser.id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : selectedUser.is_running ? (
                    <>
                      <Square size={14} /> 봇 일시 정지
                    </>
                  ) : (
                    <>
                      <Play size={14} /> 봇 거래 기동
                    </>
                  )}
                </button>

                <button
                  onClick={() => handleDeleteUser(selectedUser.id, selectedUser.username)}
                  disabled={actionUserId === selectedUser.id || selectedUser.username === 'admin'}
                  className="px-4 py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 disabled:opacity-30 disabled:cursor-not-allowed text-xs font-bold transition-all duration-200 cursor-pointer"
                  title="계정 영구 삭제"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

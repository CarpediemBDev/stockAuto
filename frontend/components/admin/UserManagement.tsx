'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Users, Loader2, Play, Square, Trash2 } from 'lucide-react';
import api from '@/lib/api';
import { toast } from "sonner";
import { getErrorMessage } from '@/lib/utils';

interface ManagedUser {
  id: number;
  username: string;
  created_at: string;
  trade_mode: string;
  telegram_enabled: boolean;
  is_running: boolean;
}

export function UserManagement() {
  const [usersList, setUsersList] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionUserId, setActionUserId] = useState<number | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/admin/users");
      setUsersList(res.data);
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
                  <tr key={user.id} className="transition-colors duration-150 hover:bg-zinc-800/10">
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
                        onClick={() => handleToggleUserBot(user.id)}
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
                        onClick={() => handleDeleteUser(user.id, user.username)}
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
    </div>
  );
}

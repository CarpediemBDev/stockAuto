'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Globe, Plus, Search, Edit2, Trash2, Check, X, Loader2 } from 'lucide-react';
import { translationAPI } from '@/lib/api';
import { getErrorMessage } from '@/lib/utils';
import { toast } from "sonner";

interface TranslationItem {
  id: number;
  ticker: string;
  name_ko: string;
}

export function TranslationManager() {
  const [translations, setTranslations] = useState<TranslationItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;
  
  const [newTicker, setNewTicker] = useState<string>("");
  const [newNameKo, setNewNameKo] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState<string>("");

  const fetchTranslations = useCallback(async () => {
    setLoading(true);
    try {
      const res = await translationAPI.getAll();
      setTranslations(res.data);
    } catch (error) {
      toast.error(`사전 데이터 로드 실패: ${getErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchTranslations();
  }, [fetchTranslations]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const tickerClean = newTicker.trim().toUpperCase();
    const nameClean = newNameKo.trim();

    if (!tickerClean || !nameClean) {
      toast.warning("티커와 한국어 이름을 모두 입력해 주세요.");
      return;
    }

    setIsSubmitting(true);
    try {
      await translationAPI.save(tickerClean, nameClean);
      toast.success(`${tickerClean} (${nameClean}) 등록 완료! (메모리 캐시 자동 핫싱크)`);
      setNewTicker("");
      setNewNameKo("");
      fetchTranslations();
    } catch (error) {
      toast.error(`번역 등록 실패: ${getErrorMessage(error)}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const startEdit = (item: TranslationItem) => {
    setEditingId(item.id);
    setEditingName(item.name_ko);
  };

  const handleUpdate = async (id: number) => {
    const nameClean = editingName.trim();
    if (!nameClean) {
      toast.warning("한국어 이름을 입력해 주세요.");
      return;
    }

    try {
      await translationAPI.update(id, nameClean);
      toast.success("번역이 수정되었으며 백엔드 캐시가 즉시 동기화되었습니다!");
      setEditingId(null);
      fetchTranslations();
    } catch (error) {
      toast.error(`수정 실패: ${getErrorMessage(error)}`);
    }
  };

  const handleDelete = async (id: number, ticker: string) => {
    if (!confirm(`${ticker} 번역 매핑을 정말 삭제하시겠습니까?\n삭제 즉시 메모리 캐시에서도 분리됩니다.`)) {
      return;
    }

    try {
      await translationAPI.delete(id);
      toast.success(`${ticker} 번역 매핑이 성공적으로 제거되었습니다.`);
      fetchTranslations();
    } catch (error) {
      toast.error(`삭제 실패: ${getErrorMessage(error)}`);
    }
  };

  const filteredTranslations = translations.filter(
    (t) =>
      t.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.name_ko.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Plus size={18} className="text-blue-400" />
            신규 주식 한글명 커스텀 등록
          </h2>
          <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
            AUTO SYNC ACTIVE
          </span>
        </div>
        
        <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div>
            <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">미국 주식 Ticker (영어)</label>
            <input
              type="text"
              placeholder="예: TSLA"
              value={newTicker}
              onChange={(e) => setNewTicker(e.target.value)}
              className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 tracking-widest font-mono uppercase"
              disabled={isSubmitting}
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">한국어 치환 이름 (한글)</label>
            <input
              type="text"
              placeholder="예: 테슬라"
              value={newNameKo}
              onChange={(e) => setNewNameKo(e.target.value)}
              className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
              disabled={isSubmitting}
            />
          </div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm py-2.5 px-4 rounded-xl shadow-lg shadow-indigo-950/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2"
          >
            {isSubmitting ? <><Loader2 size={16} className="animate-spin" />등록 중...</> : "번역 사전에 즉시 등록"}
          </button>
        </form>
      </div>

      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-4">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <Globe size={18} className="text-emerald-400" />
              주식 한글화 기준정보 데이터 목록
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              전체 사전에 저장된 번역 데이터 수: <strong className="text-emerald-400">{translations.length}개</strong>
            </p>
          </div>
          
          <div className="relative max-w-xs w-full">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
            <input
              type="text"
              placeholder="티커 또는 한글명 검색..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center gap-3">
              <Loader2 size={36} className="animate-spin text-zinc-500" />
              <span className="text-xs text-zinc-500 font-semibold">데이터베이스 로딩 중...</span>
            </div>
          ) : filteredTranslations.length === 0 ? (
            <div className="py-16 text-center">
              <Globe size={48} className="mx-auto text-zinc-700 mb-3" />
              <p className="text-sm font-semibold text-zinc-500">검색 조건에 부합하는 데이터가 없습니다.</p>
            </div>
          ) : (() => {
            const totalPages = Math.ceil(filteredTranslations.length / itemsPerPage);
            const indexOfLastItem = currentPage * itemsPerPage;
            const indexOfFirstItem = indexOfLastItem - itemsPerPage;
            const currentItems = filteredTranslations.slice(indexOfFirstItem, indexOfLastItem);
            
            return (
              <>
                <table className="min-w-full divide-y divide-zinc-800/60">
                  <thead>
                    <tr className="text-left text-xs uppercase text-zinc-500 font-bold tracking-wider">
                      <th className="px-6 py-3.5">ID</th>
                      <th className="px-6 py-3.5">티커 (심볼)</th>
                      <th className="px-6 py-3.5">한글명</th>
                      <th className="px-6 py-3.5 text-right">관리</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/40 text-sm">
                    {currentItems.map((item) => (
                      <tr key={item.id} className={`transition-colors duration-150 hover:bg-zinc-800/10 ${editingId === item.id ? "bg-blue-950/10" : ""}`}>
                        <td className="px-6 py-4 text-xs font-mono text-zinc-500 font-bold">{item.id}</td>
                        <td className="px-6 py-4 font-mono font-bold text-slate-300 tracking-wider">{item.ticker}</td>
                        <td className="px-6 py-4">
                          {editingId === item.id ? (
                            <input
                              type="text"
                              value={editingName}
                              onChange={(e) => setEditingName(e.target.value)}
                              className="bg-[#05080f] border border-blue-500/50 rounded-lg px-3 py-1 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                              onKeyDown={(e) => {
                                if (e.key === "Enter") handleUpdate(item.id);
                                if (e.key === "Escape") setEditingId(null);
                              }}
                              autoFocus
                            />
                          ) : (
                            <span className="text-slate-100 font-medium">{item.name_ko}</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-right space-x-2">
                          {editingId === item.id ? (
                            <>
                              <button onClick={() => handleUpdate(item.id)} className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20" title="저장"><Check size={16} /></button>
                              <button onClick={() => setEditingId(null)} className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700" title="취소"><X size={16} /></button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => startEdit(item)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20" title="수정"><Edit2 size={16} /></button>
                              <button onClick={() => handleDelete(item.id, item.ticker)} className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20" title="삭제"><Trash2 size={16} /></button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                
                {totalPages > 1 && (
                  <div className="flex flex-col sm:flex-row items-center justify-between border-t border-zinc-800/80 pt-5 mt-4 gap-4">
                    <span className="text-xs text-zinc-500 font-semibold">
                      Showing <strong className="text-zinc-300">{indexOfFirstItem + 1}</strong> to <strong className="text-zinc-300">{Math.min(indexOfLastItem, filteredTranslations.length)}</strong> of <strong className="text-zinc-300">{filteredTranslations.length}</strong> items
                    </span>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))} disabled={currentPage === 1} className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 text-zinc-400 hover:text-white transition-all">Previous</button>
                      <button type="button" className="w-9 h-9 rounded-xl text-xs font-bold transition-all flex items-center justify-center bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg border border-teal-500/20">{currentPage}</button>
                      <button onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))} disabled={currentPage === totalPages} className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 text-zinc-400 hover:text-white transition-all">Next</button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      </div>
    </div>
  );
}

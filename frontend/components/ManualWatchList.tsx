'use client';

import React, { useState, useCallback } from 'react';
import { Eye, Plus, Trash2 } from 'lucide-react';
import { watchlistAPI, translationAPI } from '@/lib/api';
import { usePolling } from '@/hooks/usePolling';
import { getErrorMessage } from '@/lib/utils';

interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string;
}

interface TranslationItem {
  ticker: string;
  name_ko: string;
}

const ManualWatchList = () => {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [allTranslations, setAllTranslations] = useState<TranslationItem[]>([]);

  const fetchWatchList = React.useCallback(async () => {
    try {
      const res = await watchlistAPI.getAll();
      setItems(res.data);
    } catch (error) {
      console.error('Failed to fetch watchlist:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTranslations = useCallback(async () => {
    try {
      const res = await translationAPI.getAll();
      setAllTranslations(res.data);
    } catch (error) {
      console.error('Failed to fetch translations for autocomplete:', error);
    }
  }, []);

  const handleToggleAddForm = useCallback(() => {
    setShowAddForm(prev => {
      const next = !prev;
      if (next) {
        fetchTranslations();
      }
      return next;
    });
  }, [fetchTranslations]);

  const handleAdd = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    const rawValue = inputValue.trim();
    if (!rawValue) return;

    // 첫 번째 단어는 무조건 대문자 Ticker로 취급하고, 그 뒤에 오는 텍스트는 Name으로 처리합니다.
    const parts = rawValue.split(/\s+/);
    const tickerClean = parts[0].toUpperCase();
    const nameClean = parts.slice(1).join(' ') || tickerClean;

    setIsSubmitting(true);
    try {
      await watchlistAPI.add(tickerClean, nameClean);
      setInputValue('');
      setShowAddForm(false);
      await fetchWatchList();
    } catch (error) {
      console.error('Failed to add ticker:', error);
      // 백엔드가 던져주는 세밀한 검증 에러 메시지(예: 영문 Ticker 규격 미달, 상장 미확인 등)를 사용자에게 즉시 전달!
      alert(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }, [inputValue, fetchWatchList]);

  const handleSelectSuggestion = useCallback(async (ticker: string, nameKo: string) => {
    setIsSubmitting(true);
    try {
      await watchlistAPI.add(ticker, nameKo);
      setInputValue('');
      setShowAddForm(false);
      await fetchWatchList();
    } catch (error) {
      console.error('Failed to add suggestion:', error);
      alert(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }, [fetchWatchList]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      await watchlistAPI.delete(id);
      await fetchWatchList();
    } catch (error) {
      console.error('Failed to delete ticker:', error);
    }
  }, [fetchWatchList]);

  usePolling(fetchWatchList, 30000);

  // 실시간 필터링 Suggestions 계산
  const query = inputValue.trim().toLowerCase();
  const suggestions = query
    ? allTranslations.filter(t => 
        t.ticker.toLowerCase().includes(query) || 
        t.name_ko.toLowerCase().includes(query)
      ).slice(0, 5)
    : [];

  if (loading) return <div className="h-64 bg-slate-900/50 rounded-2xl animate-pulse"></div>;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
        <div className="flex items-center space-x-2">
          <Eye size={16} className="text-blue-400" />
          <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider">{"User's Watch List"}</h3>
        </div>
        <button 
          onClick={handleToggleAddForm}
          className={`p-1 hover:bg-slate-800 rounded transition-all duration-200 ${showAddForm ? 'text-blue-400 bg-slate-800/80 rotate-45' : 'text-slate-500'}`}
        >
          <Plus size={16} />
        </button>
      </div>

      {showAddForm && (
        <form onSubmit={handleAdd} className="p-4 border-b border-slate-800/60 bg-slate-950/40 transition-all duration-300">
          <div className="space-y-1.5">
            <label className="block text-[10px] text-slate-500 font-semibold uppercase tracking-wider">
              Add Stock Manually
            </label>
            <div className="flex gap-2 relative">
              <input
                type="text"
                required
                placeholder="e.g. AAPL or AAPL Apple"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs font-medium text-slate-100 placeholder-slate-600 focus:outline-none focus:border-blue-500 transition-colors"
              />
              <button
                type="submit"
                disabled={isSubmitting || !inputValue.trim()}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-xs font-bold transition-all active:scale-95 flex items-center justify-center whitespace-nowrap min-w-[70px]"
              >
                {isSubmitting ? "Adding..." : "Add"}
              </button>

              {/* 실시간 한글명/티커 자동 완성 오토컴플릿 드롭다운 (유저 캡처 구현) */}
              {suggestions.length > 0 && (
                <div className="absolute left-0 right-[78px] top-full mt-1.5 bg-slate-950/95 backdrop-blur-md border border-slate-850 rounded-xl shadow-2xl z-50 overflow-hidden divide-y divide-slate-800/40">
                  {suggestions.map((sug) => {
                    // 유저 캡처 화면처럼 매칭된 검색어를 주황색/금색(amber)으로 하이라이팅하여 가독성 극대화!
                    const nameParts = sug.name_ko.split(new RegExp(`(${query})`, 'gi'));
                    return (
                      <div
                        key={sug.ticker}
                        onClick={() => handleSelectSuggestion(sug.ticker, sug.name_ko)}
                        className="px-3.5 py-2.5 hover:bg-slate-800/60 transition-colors cursor-pointer flex items-center justify-between text-xs group"
                      >
                        <div className="flex items-center space-x-3">
                          <span className="font-mono font-bold text-slate-400 group-hover:text-slate-200 w-12">{sug.ticker}</span>
                          <span className="text-slate-300 group-hover:text-white font-medium">
                            {nameParts.map((part, i) => 
                              part.toLowerCase() === query 
                                ? <span key={i} className="text-amber-500 font-bold">{part}</span>
                                : <span key={i}>{part}</span>
                            )}
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-500 group-hover:text-slate-400 font-medium">나스닥</span>
                      </div>
                    );
                  })}
                  <div className="px-3.5 py-1.5 bg-slate-950/40 text-[9px] text-slate-600 flex items-center justify-between">
                    <span>ⓘ 사전 매핑된 한글명을 클릭하면 즉시 등록됩니다.</span>
                    <span className="text-slate-700">StockAuto i18n</span>
                  </div>
                </div>
              )}
            </div>
            <p className="text-[10px] text-slate-600">
              * 첫 단어는 티커로, 뒤의 단어는 이름으로 자동 처리됩니다 (예: <span className="text-slate-500 font-bold">TSLA Tesla</span>)
            </p>
          </div>
        </form>
      )}
      
      <div className="overflow-x-auto min-h-[300px]">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800/50 text-[11px] uppercase tracking-tighter">
              <th className="px-5 py-3 font-semibold">Ticker</th>
              <th className="px-2 py-3 font-semibold">Live Score</th>
              <th className="px-5 py-3 font-semibold text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/30">
            {items.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-5 py-10 text-center text-slate-600 italic">No manual watch items.</td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className="hover:bg-slate-800/30 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="flex flex-col">
                      <span className="font-bold text-slate-200">{item.ticker}</span>
                      <span className="text-[10px] text-slate-500">{item.ticker_name}</span>
                    </div>
                  </td>
                  <td className="px-2 py-4">
                    {/* 수동 관심종목의 현재 점수 시각화 (예시 데이터) */}
                    <div className="w-full h-1.5 bg-slate-800 rounded-full max-w-[80px]">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: '65%' }}></div>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <button 
                      onClick={() => handleDelete(item.id)}
                      className="text-slate-600 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all cursor-pointer"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ManualWatchList;

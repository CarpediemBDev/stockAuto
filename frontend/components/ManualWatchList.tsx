'use client';

import React, { useState, useCallback } from 'react';
import { Eye, Plus, Trash2, Bot } from 'lucide-react';
import BotSignals from '@/components/BotSignals';
import { watchlistAPI, translationAPI } from '@/lib/api';
import useSWR from 'swr';
import { fetcher } from '@/lib/api';
import { reportHandledError } from '@/lib/utils';
import { toast } from 'sonner';

interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string;
}

interface TranslationItem {
  ticker: string;
  name_ko: string;
}

interface ScannerSignal {
  ticker: string;
  signal_score: number;
  source?: string[];
}

const ManualWatchList = () => {
  const { data: watchData, isLoading: watchLoading, mutate: mutateWatchList } = useSWR('/watchlist', fetcher, { refreshInterval: 15000 });
  const { data: scannerData, isLoading: scannerLoading } = useSWR('/scanner/latest', fetcher, { refreshInterval: 15000 });

  const items: WatchItem[] = Array.isArray(watchData) ? watchData : (watchData?.data || []);
  const signals: ScannerSignal[] = Array.isArray(scannerData) ? scannerData : (scannerData?.data || []);
  const loading = watchLoading || scannerLoading;

  const [showAddForm, setShowAddForm] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [allTranslations, setAllTranslations] = useState<TranslationItem[]>([]);
  const [activeTab, setActiveTab] = useState<'user' | 'bot'>('user');

  const fetchTranslations = useCallback(async () => {
    try {
      const res = await translationAPI.getAll();
      setAllTranslations(res.data);
    } catch (error) {
      reportHandledError('Failed to fetch translations for autocomplete', error);
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
      await mutateWatchList();
      toast.success(`${tickerClean} (${nameClean})이(가) 관심종목에 추가되었습니다.`);
    } catch (error) {
      toast.error(reportHandledError('Failed to add ticker', error));
    } finally {
      setIsSubmitting(false);
    }
  }, [inputValue, mutateWatchList]);

  const handleSelectSuggestion = useCallback(async (ticker: string, nameKo: string) => {
    setIsSubmitting(true);
    try {
      await watchlistAPI.add(ticker, nameKo);
      setInputValue('');
      setShowAddForm(false);
      await mutateWatchList();
      toast.success(`${ticker} (${nameKo})이(가) 관심종목에 추가되었습니다.`);
    } catch (error) {
      toast.error(reportHandledError('Failed to add suggestion', error));
    } finally {
      setIsSubmitting(false);
    }
  }, [mutateWatchList]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      await watchlistAPI.delete(id);
      await mutateWatchList();
      toast.success("관심종목에서 성공적으로 제거되었습니다.");
    } catch (error) {
      const msg = reportHandledError('Failed to delete ticker', error);
      toast.error(`삭제 실패: ${msg}`);
    }
  }, [mutateWatchList]);

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
      <div className="px-3 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
        <div className="flex items-center space-x-6 px-2">
          <button 
            onClick={() => setActiveTab('user')}
            className={`flex items-center space-x-2 py-3.5 text-xs font-bold uppercase tracking-wider transition-all border-b-2 -mb-[1px] ${
              activeTab === 'user' 
                ? 'border-white text-white' 
                : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <Eye size={16} className={activeTab === 'user' ? "text-blue-400" : ""} />
            <span>MY LIST</span>
          </button>
          <button 
            onClick={() => setActiveTab('bot')}
            className={`flex items-center space-x-2 py-3.5 text-xs font-bold uppercase tracking-wider transition-all border-b-2 -mb-[1px] ${
              activeTab === 'bot' 
                ? 'border-white text-white' 
                : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-600'
            }`}
          >
            <Bot size={16} className={activeTab === 'bot' ? "text-amber-400" : ""} />
            <span>BOT SIGNALS</span>
          </button>
        </div>
        {activeTab === 'user' && (
          <button 
            onClick={handleToggleAddForm}
            className={`p-1.5 hover:bg-slate-800 rounded transition-all duration-200 ${showAddForm ? 'text-blue-400 bg-slate-800/80 rotate-45' : 'text-slate-400 hover:text-slate-200'}`}
          >
            <Plus size={18} />
          </button>
        )}
      </div>

      {showAddForm && activeTab === 'user' && (
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
      
      {activeTab === 'user' ? (
        <div className="overflow-x-auto min-h-[300px]">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800/50 text-[10px] uppercase tracking-wider">
                <th className="px-5 py-3 font-semibold">Ticker</th>
                <th className="px-2 py-3 font-semibold">SIGNAL SCORE</th>
                <th className="px-5 py-3 font-semibold text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/30">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-5 py-12 text-center text-slate-500 text-xs">
                    <p className="mb-1">관심종목이 비어있습니다.</p>
                    <p className="text-[10px] text-slate-600">위의 + 버튼을 눌러 티커를 추가하세요.</p>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-800/20 transition-colors group">
                    <td className="px-5 py-3">
                      <div className="flex flex-col">
                        <span className="font-bold text-slate-200 text-sm tracking-tight">{item.ticker}</span>
                        <span className="text-[10px] text-slate-500 truncate max-w-[120px]">{item.ticker_name}</span>
                      </div>
                    </td>
                    <td className="px-2 py-3">
                      {/* Premium Score Visualization */}
                      {(() => {
                        const sig = signals.find(s => s.ticker.toUpperCase() === item.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
                        if (sig) {
                          const score = sig.signal_score;
                          const scoreColor = score >= 80 ? 'text-rose-500 bg-rose-500/10 border-rose-500/20' : 
                                            score >= 60 ? 'text-amber-500 bg-amber-500/10 border-amber-500/20' : 
                                            'text-blue-400 bg-blue-500/10 border-blue-500/20';
                          const barColor = score >= 80 ? 'bg-rose-500' : score >= 60 ? 'bg-amber-500' : 'bg-blue-400';
                          return (
                            <div className="flex items-center space-x-3">
                              <div className={`w-8 h-8 rounded-full border flex items-center justify-center text-[11px] font-black ${scoreColor}`}>
                                {score}
                              </div>
                              <div className="flex-1 max-w-[50px] h-1.5 bg-slate-800 rounded-full overflow-hidden hidden sm:block">
                                <div className={`h-full ${barColor} rounded-full`} style={{ width: `${score}%` }}></div>
                              </div>
                            </div>
                          );
                        } else {
                          return (
                            <div className="flex items-center space-x-2 py-1.5">
                              <div className="w-1.5 h-1.5 rounded-full bg-slate-600 animate-pulse"></div>
                              <span className="text-[10px] text-slate-500 font-medium tracking-tight">대기중</span>
                            </div>
                          );
                        }
                      })()}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button 
                        onClick={() => handleDelete(item.id)}
                        className="p-1.5 text-slate-600 hover:text-rose-400 hover:bg-rose-400/10 rounded-md transition-all opacity-40 group-hover:opacity-100 cursor-pointer"
                        title="관심종목 삭제"
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
      ) : (
        <BotSignals hideHeader={true} />
      )}
    </div>
  );
};

export default ManualWatchList;

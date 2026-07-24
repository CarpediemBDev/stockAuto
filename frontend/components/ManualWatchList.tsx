'use client';

import React, { useState, useCallback } from 'react';
import { Eye, Plus, Trash2, Bot } from 'lucide-react';
import BotSignals from '@/components/BotSignals';
import { translationAPI } from '@/lib/api';
import useSWR from 'swr';
import { pollInterval } from '@/lib/sse';
import { fetcher } from '@/lib/api';
import { reportHandledError, getScoreColor, getScoreBarColor } from '@/lib/utils';
import { useWatchlistActions } from '@/hooks/useWatchlistActions';
import { useTranslations } from "next-intl";

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
  const t = useTranslations("scanner");
  const {
    items,
    isLoading: watchLoading,
    addToWatchlist,
    deleteFromWatchlist,
    deletingId,
  } = useWatchlistActions();
  const { data: scannerData, isLoading: scannerLoading } = useSWR('/scanner/latest', fetcher, { refreshInterval: pollInterval(15000) });

  const signals: ScannerSignal[] = Array.isArray(scannerData) ? scannerData : (scannerData?.signals || []);
  
  const sortedItems = [...items].sort((a, b) => {
    const sigA = signals.find(s => s.ticker.toUpperCase() === a.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
    const sigB = signals.find(s => s.ticker.toUpperCase() === b.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
    const scoreA = sigA ? sigA.signal_score : 0;
    const scoreB = sigB ? sigB.signal_score : 0;
    return scoreB - scoreA;
  });

  const loading = watchLoading || scannerLoading;

  const [showAddForm, setShowAddForm] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [allTranslations, setAllTranslations] = useState<TranslationItem[]>([]);
  const [activeTab, setActiveTab] = useState<'user' | 'bot'>('user');
  const [isExpanded, setIsExpanded] = useState(false);

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
      await addToWatchlist(tickerClean, nameClean);
      setInputValue('');
      setShowAddForm(false);
    } catch {
      // useWatchlistActions already reports the failure to the user.
    } finally {
      setIsSubmitting(false);
    }
  }, [addToWatchlist, inputValue]);

  const handleSelectSuggestion = useCallback(async (ticker: string, nameKo: string) => {
    setIsSubmitting(true);
    try {
      await addToWatchlist(ticker, nameKo);
      setInputValue('');
      setShowAddForm(false);
    } catch {
      // useWatchlistActions already reports the failure to the user.
    } finally {
      setIsSubmitting(false);
    }
  }, [addToWatchlist]);

  const handleDelete = useCallback(async (id: number) => {
    try {
      await deleteFromWatchlist(id);
    } catch {
      // useWatchlistActions already reports the failure to the user.
    }
  }, [deleteFromWatchlist]);

  // 실시간 필터링 Suggestions 계산
  const query = inputValue.trim().toLowerCase();
  const suggestions = query
    ? allTranslations.filter(t => 
        t.ticker.toLowerCase().includes(query) || 
        t.name_ko.toLowerCase().includes(query)
      ).slice(0, 5)
    : [];

  if (loading) return <div className="h-64 bg-zinc-900/50 rounded-2xl animate-pulse"></div>;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
      <div className="px-3 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50">
        <div className="flex items-center space-x-6 px-2">
          <button 
            onClick={() => setActiveTab('user')}
            className={`flex items-center space-x-2 py-3.5 text-xs font-bold uppercase tracking-wider transition-all border-b-2 -mb-[1px] ${
              activeTab === 'user' 
                ? 'border-white text-white' 
                : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
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
                : 'border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600'
            }`}
          >
            <Bot size={16} className={activeTab === 'bot' ? "text-amber-400" : ""} />
            <span>BOT SIGNALS</span>
          </button>
        </div>
        {activeTab === 'user' && (
          <button 
            onClick={handleToggleAddForm}
            className={`p-1.5 hover:bg-zinc-800 rounded transition-all duration-200 ${showAddForm ? 'text-blue-400 bg-zinc-800/80 rotate-45' : 'text-zinc-400 hover:text-zinc-200'}`}
          >
            <Plus size={18} />
          </button>
        )}
      </div>

      {showAddForm && activeTab === 'user' && (
        <form onSubmit={handleAdd} className="p-4 border-b border-zinc-800/60 bg-zinc-950/40 transition-all duration-300">
          <div className="space-y-1.5">
            <label className="block text-[11px] text-zinc-500 font-semibold uppercase tracking-wider">
              Add Stock Manually
            </label>
            <div className="flex gap-2 relative">
              <input
                type="text"
                required
                placeholder="e.g. AAPL or AAPL Apple"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-xs font-medium text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-blue-500 transition-colors"
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
                <div className="absolute left-0 right-[78px] top-full mt-1.5 bg-zinc-950/95 backdrop-blur-md border border-zinc-850 rounded-xl shadow-2xl z-50 overflow-hidden divide-y divide-zinc-800/40">
                  {suggestions.map((sug) => {
                    // 유저 캡처 화면처럼 매칭된 검색어를 주황색/금색(amber)으로 하이라이팅하여 가독성 극대화!
                    const nameParts = sug.name_ko.split(new RegExp(`(${query})`, 'gi'));
                    return (
                      <div
                        key={sug.ticker}
                        onClick={() => handleSelectSuggestion(sug.ticker, sug.name_ko)}
                        className="px-3.5 py-2.5 hover:bg-zinc-800/60 transition-colors cursor-pointer flex items-center justify-between text-xs group"
                      >
                        <div className="flex items-center space-x-3">
                          <span className="font-mono font-bold text-zinc-400 group-hover:text-zinc-200 w-12">{sug.ticker}</span>
                          <span className="text-zinc-300 group-hover:text-white font-medium">
                            {nameParts.map((part, i) => 
                              part.toLowerCase() === query 
                                ? <span key={i} className="text-amber-500 font-bold">{part}</span>
                                : <span key={i}>{part}</span>
                            )}
                          </span>
                        </div>
                        <span className="text-[11px] text-zinc-500 group-hover:text-zinc-400 font-medium">{t("watchlist.nasdaq")}</span>
                      </div>
                    );
                  })}
                  <div className="px-3.5 py-1.5 bg-zinc-950/40 text-[11px] text-zinc-600 flex items-center justify-between">
                    <span>{t("watchlist.autocomplete_hint")}</span>
                    <span className="text-zinc-700">StockAuto i18n</span>
                  </div>
                </div>
              )}
            </div>
            <p className="text-[11px] text-zinc-600">
              * 첫 단어는 티커로, 뒤의 단어는 이름으로 자동 처리됩니다 (예: <span className="text-zinc-500 font-bold">TSLA Tesla</span>)
            </p>
          </div>
        </form>
      )}
      
      {activeTab === 'user' ? (
        <div className="flex flex-col">
          {/* 모바일/태블릿 접이식 요약 (lg 미만에서만 표시) */}
          <div className="lg:hidden p-4 border-b border-zinc-800/50">
            <div className="flex justify-between items-center mb-3">
              <span className="text-[11px] font-bold text-zinc-400">{t("watchlist.summary_title")}</span>
              <button 
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-[11px] text-blue-400 bg-blue-500/10 px-2 py-1 rounded font-bold"
              >
                {isExpanded ? t("watchlist.collapse") : t("watchlist.expand")}
              </button>
            </div>
            {!isExpanded && (
              <div className="flex flex-wrap gap-2">
                {sortedItems.filter(item => {
                  const sig = signals.find(s => s.ticker.toUpperCase() === item.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
                  return sig && sig.signal_score > 0;
                }).map(item => {
                  const sig = signals.find(s => s.ticker.toUpperCase() === item.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
                  const scoreColorClass = getScoreColor(sig!.signal_score);
                  return (
                    <span key={item.id} className={`text-[11px] px-2 py-1 rounded border font-black ${scoreColorClass}`}>
                      {item.ticker} {sig!.signal_score}
                    </span>
                  );
                })}
                {sortedItems.filter(item => {
                  const sig = signals.find(s => s.ticker.toUpperCase() === item.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
                  return sig && sig.signal_score > 0;
                }).length === 0 && (
                  <span className="text-[11px] text-zinc-500">{t("watchlist.no_signal")}</span>
                )}
              </div>
            )}
          </div>

          <div className={`overflow-x-auto min-h-[300px] ${!isExpanded ? 'hidden lg:block' : 'block'}`}>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800/50 text-[11px] uppercase tracking-wider">
                  <th className="px-5 py-3 font-semibold">Ticker</th>
                  <th className="px-2 py-3 font-semibold">SIGNAL SCORE</th>
                  <th className="px-5 py-3 font-semibold text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/30">
                {sortedItems.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-5 py-12 text-center text-zinc-500 text-xs">
                      <p className="mb-1">{t("watchlist.empty_title")}</p>
                      <p className="text-[11px] text-zinc-600">{t("watchlist.empty_hint")}</p>
                    </td>
                  </tr>
                ) : (
                  sortedItems.map((item) => {
                    const sig = signals.find(s => s.ticker.toUpperCase() === item.ticker.toUpperCase() && (!s.source || s.source.includes("WATCHLIST")));
                    const hasSignal = sig && sig.signal_score > 0;
                    
                    return (
                    <tr key={item.id} className="hover:bg-zinc-800/20 transition-colors group">
                      <td className={`px-5 ${hasSignal ? 'py-3' : 'py-1.5'}`}>
                        <div className="flex flex-col">
                          <span className={`font-bold tracking-tight ${hasSignal ? 'text-zinc-200 text-sm' : 'text-zinc-500 text-xs'}`}>{item.ticker}</span>
                          {hasSignal && <span className="text-[11px] text-zinc-500 truncate max-w-[120px]">{item.ticker_name}</span>}
                        </div>
                      </td>
                      <td className={`px-2 ${hasSignal ? 'py-3' : 'py-1.5'}`}>
                        {/* Premium Score Visualization */}
                        {hasSignal ? (
                          <div className="flex items-center space-x-3">
                            <div className={`w-8 h-8 rounded-full border flex items-center justify-center text-[11px] font-black ${getScoreColor(sig.signal_score)}`}>
                              {sig.signal_score}
                            </div>
                            <div className="flex-1 max-w-[50px] h-1.5 bg-zinc-800 rounded-full overflow-hidden hidden sm:block border border-zinc-800">
                              <div className={`h-full rounded-full transition-all duration-1000 ${getScoreBarColor(sig.signal_score)}`} style={{ width: `${sig.signal_score}%` }}></div>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center space-x-2 py-0.5">
                            <div className="w-1.5 h-1.5 rounded-full bg-zinc-700"></div>
                            <span className="text-[11px] text-zinc-600 font-medium tracking-tight">{t("watchlist.waiting")}</span>
                          </div>
                        )}
                      </td>
                      <td className={`px-5 text-right ${hasSignal ? 'py-3' : 'py-1.5'}`}>
                        <button 
                          onClick={() => handleDelete(item.id)}
                          disabled={deletingId === item.id}
                          className="p-1.5 text-zinc-600 hover:text-rose-400 hover:bg-rose-400/10 rounded-md transition-all opacity-40 group-hover:opacity-100 cursor-pointer"
                          title={t("watchlist.delete_title")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <BotSignals hideHeader={true} />
      )}
    </div>
  );
};

export default ManualWatchList;

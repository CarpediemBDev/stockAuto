"use client";

import { useEffect, useState, useCallback } from "react";
import { watchlistAPI, isCancel } from "@/lib/api";
import { Plus, Trash2, Search, Loader2, Star } from "lucide-react";
import { toast } from "sonner";
import { cn, getErrorMessage } from "@/lib/utils";

interface WatchListItem {
  id: number;
  ticker: string;
  ticker_name: string | null;
}

interface WatchListManagerProps {
  refreshKey?: number;
  onRefreshScanner?: () => void;
}

export function WatchListManager({ refreshKey: externalRefreshKey, onRefreshScanner }: WatchListManagerProps) {
  const [items, setItems] = useState<WatchListItem[]>([]);
  const [newTicker, setNewTicker] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchWatchlist = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    try {
      const res = await watchlistAPI.getAll({ signal });
      setItems(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      console.error("Failed to fetch watchlist:", getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      fetchWatchlist(controller.signal);
    }, 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [fetchWatchlist, refreshKey, externalRefreshKey]);

  const refresh = () => setRefreshKey((k) => k + 1);

  const addItem = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!newTicker.trim()) return;

    setIsAdding(true);
    try {
      await watchlistAPI.add(newTicker.toUpperCase().trim(), "");
      setNewTicker("");
      refresh();
      if (onRefreshScanner) onRefreshScanner();
    } catch (error) {
      const message = getErrorMessage(error);
      toast.error(message);
    } finally {
      setIsAdding(false);
    }
  };

  const removeItem = async (id: number) => {
    try {
      await watchlistAPI.delete(id);
      refresh();
      if (onRefreshScanner) onRefreshScanner();
    } catch (error) {
      toast.error("종목 삭제에 실패했습니다.");
      console.error("Failed to delete item:", getErrorMessage(error));
    }
  };

  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl flex flex-col h-full shadow-xl overflow-hidden">
      {/* 헤더 */}
      <div className="p-5 border-b border-zinc-800/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star size={18} className="text-amber-400 fill-amber-400/20" />
          <h2 className="text-base font-bold text-white tracking-tight">관심종목</h2>
          <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded-full font-mono">
            {items.length}
          </span>
        </div>
      </div>

      {/* 종목 추가 입력 필드 */}
      <div className="p-4 border-b border-zinc-800/40">
        <form onSubmit={addItem} className="relative">
          <input
            type="text"
            value={newTicker}
            onChange={(e) => setNewTicker(e.target.value)}
            placeholder="티커 추가 (예: TSLA)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/50 transition-all"
          />
          <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-600" />
          <button
            type="submit"
            disabled={isAdding || !newTicker.trim()}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-blue-400 hover:bg-blue-500/10 rounded-lg disabled:opacity-0 transition-all"
          >
            {isAdding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={16} />}
          </button>
        </form>
      </div>

      {/* 종목 리스트 */}
      <div className="flex-1 overflow-y-auto no-scrollbar">
        {isLoading && items.length === 0 ? (
          <div className="flex justify-center py-10">
            <Loader2 size={20} className="text-zinc-700 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="py-12 px-6 text-center">
            <p className="text-zinc-600 text-xs leading-relaxed">
              등록된 관심종목이 없습니다.<br/>위에서 종목을 검색하여 추가하세요.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/30">
            {items.map((item) => (
              <div
                key={item.id}
                className="group flex items-center justify-between p-4 hover:bg-zinc-800/30 transition-all"
              >
                <div className="flex flex-col min-w-0">
                  <span className="font-bold text-zinc-200 text-sm tracking-tight truncate">
                    {item.ticker_name || item.ticker}
                  </span>
                  <span className="text-[10px] text-zinc-500 font-mono tracking-wider">{item.ticker}</span>
                </div>
                
                <div className="flex items-center gap-3">
                  {/* 여기서는 Mock 데이터를 표시하거나 나중에 실제 가격 API 연결 가능 */}
                  <div className="flex flex-col items-end">
                    <span className="text-xs font-mono font-medium text-zinc-300">WATCH</span>
                    <span className="text-[9px] text-zinc-600">Saved</span>
                  </div>
                  
                  <button
                    onClick={() => removeItem(item.id)}
                    className="p-1.5 text-zinc-700 hover:text-rose-400 hover:bg-rose-500/10 rounded-md opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 하단 정보 */}
      <div className="p-4 bg-zinc-950/30 border-t border-zinc-800/80">
        <p className="text-[10px] text-zinc-600 text-center uppercase tracking-widest">
          Personal Watchlist Panel
        </p>
      </div>
    </div>
  );
}

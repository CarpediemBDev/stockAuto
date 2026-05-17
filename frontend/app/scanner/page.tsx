'use client';

import { OverseasScanner } from "@/components/OverseasScanner";
import ManualWatchList from "@/components/ManualWatchList";
import { Search, Zap, Eye } from "lucide-react";
import { useState, useCallback, useEffect } from "react";
import { watchlistAPI } from "@/lib/api";

interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string | null;
}

export default function ScannerPage() {
  const [watchlistKey, setWatchlistKey] = useState(0);
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);

  useEffect(() => {
    let isMounted = true;

    async function loadWatchlist() {
      try {
        const res = await watchlistAPI.getAll();
        if (isMounted) {
          setWatchlistTickers(res.data.map((item: WatchItem) => item.ticker));
        }
      } catch (error) {
        console.error("Failed to fetch watchlist tickers", error);
      }
    }

    loadWatchlist();

    return () => {
      isMounted = false;
    };
  }, [watchlistKey]);

  const handleAddToWatchlist = useCallback(async (ticker: string, name: string) => {
    try {
      await watchlistAPI.add(ticker, name);
      setWatchlistKey(prev => prev + 1);
    } catch (error) {
      console.error("Failed to add to watchlist", error);
      alert("관심종목 추가에 실패했습니다.");
    }
  }, []);

  return (
    <div className="min-h-screen bg-black p-6 pt-12">
      <div className="max-w-[1600px] mx-auto">
        <header className="mb-10">
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-orange-500 mb-2">
            Market Scanner
          </h1>
          <p className="text-zinc-400 font-medium">봇의 실시간 정밀 스캔 결과와 나의 관심종목을 통합 관리합니다.</p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-8">
            <OverseasScanner 
              onAddToWatchlist={handleAddToWatchlist} 
              watchlistTickers={watchlistTickers}
            />
          </div>
          <div className="lg:col-span-4">
            <div className="sticky top-6 space-y-4">
              <h2 className="text-xl font-bold text-slate-100 flex items-center">
                <Eye size={20} className="text-blue-400 mr-3" />
                {"사용자 관심종목 (User's View)"}
              </h2>
              <ManualWatchList key={watchlistKey} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

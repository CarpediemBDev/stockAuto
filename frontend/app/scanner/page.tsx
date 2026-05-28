'use client';

import { OverseasScanner } from "@/components/OverseasScanner";
import { SwingPredictorCard } from "@/components/SwingPredictorCard";
import ManualWatchList from "@/components/ManualWatchList";
import { useState, useCallback, useEffect, startTransition } from "react";
import { watchlistAPI } from "@/lib/api";
import { useRouter } from "next/navigation";

interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string | null;
}

export default function ScannerPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [watchlistKey, setWatchlistKey] = useState(0);
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"15m" | "swing">("15m");

  // Auth Guard
  useEffect(() => {
    const token = localStorage.getItem("stockauto_token");
    if (!token) {
      router.push("/login");
    } else {
      startTransition(() => {
        setIsAuthenticated(true);
      });
    }
  }, [router]);


  useEffect(() => {
    if (!isAuthenticated) return;
    
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
  }, [watchlistKey, isAuthenticated]);

  const handleAddToWatchlist = useCallback(async (ticker: string, name: string) => {
    try {
      await watchlistAPI.add(ticker, name);
      setWatchlistKey(prev => prev + 1);
    } catch (error) {
      console.error("Failed to add to watchlist", error);
    }
  }, []);

  if (!isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-black flex items-center justify-center text-zinc-400 text-sm">
        인증 정보 확인 중...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black p-6 pt-12">
      <div className="max-w-[1600px] mx-auto">
        <header className="mb-10">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-orange-500 mb-2">
                Market Scanner
              </h1>
              <p className="text-zinc-400 font-medium">봇의 실시간 정밀 스캔 결과와 나의 관심종목을 통합 관리합니다.</p>
            </div>
            
            {/* 2-Tab Segmented Control */}
            <div className="flex bg-zinc-900 border border-zinc-800 p-1 rounded-xl shadow-inner">
              <button
                onClick={() => setActiveTab("15m")}
                className={`px-6 py-2 rounded-lg text-sm font-bold transition-all duration-300 ${
                  activeTab === "15m"
                    ? "bg-zinc-800 text-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.15)]"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                15m 단타(기존)
              </button>
              <button
                onClick={() => setActiveTab("swing")}
                className={`px-6 py-2 rounded-lg text-sm font-bold transition-all duration-300 ${
                  activeTab === "swing"
                    ? "bg-zinc-800 text-indigo-400 shadow-[0_0_15px_rgba(99,102,241,0.15)]"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                내일 세력돌파 예측(스윙)
              </button>
            </div>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-8">
            {activeTab === "15m" ? (
              <OverseasScanner 
                onAddToWatchlist={handleAddToWatchlist} 
                watchlistTickers={watchlistTickers}
              />
            ) : (
              <SwingPredictorCard />
            )}
          </div>
          <div className="lg:col-span-4">
            <div className="sticky top-6 space-y-4">
              <ManualWatchList key={watchlistKey} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

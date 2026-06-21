'use client';

import { OverseasScanner } from "@/components/OverseasScanner";
import { SwingPredictorCard } from "@/components/SwingPredictorCard";
import ManualWatchList from "@/components/ManualWatchList";
import { useState, useCallback, useEffect } from "react";
import { useAuthStore } from "@/store/authStore";
import { watchlistAPI } from "@/lib/api";
import { useRouter } from "next/navigation";
import { reportHandledError } from "@/lib/utils";

interface WatchItem {
  id: number;
  ticker: string;
  ticker_name: string | null;
}

export default function ScannerPage() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuthStore();
  const [watchlistKey, setWatchlistKey] = useState(0);
  const [watchlistTickers, setWatchlistTickers] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"15m" | "swing">("15m");

  // Auth Guard
  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.push("/login");
    }
  }, [isInitialized, isAuthenticated, router]);


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
        reportHandledError("Failed to fetch watchlist tickers", error);
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
      reportHandledError("Failed to add to watchlist", error);
    }
  }, []);

  if (!isInitialized || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-black flex items-center justify-center text-zinc-400 text-sm">
        인증 정보 확인 중...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-[1600px] mx-auto px-6 py-8 md:py-12">
        <header className="mb-8">
          <div>
            <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-zinc-200 to-zinc-400 tracking-tight mb-2">
              마켓 스캐너
            </h1>
            <p className="text-zinc-400 font-medium">봇의 실시간 정밀 스캔 결과와 나의 관심종목을 통합 관리합니다.</p>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-9 min-w-0">
            {activeTab === "15m" ? (
              <OverseasScanner
                onAddToWatchlist={handleAddToWatchlist}
                watchlistTickers={watchlistTickers}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
              />
            ) : (
              <SwingPredictorCard
                activeTab={activeTab}
                setActiveTab={setActiveTab}
              />
            )}
          </div>
          <div className="lg:col-span-3 min-w-0">
            <div className="sticky top-6 space-y-4">
              <ManualWatchList key={watchlistKey} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

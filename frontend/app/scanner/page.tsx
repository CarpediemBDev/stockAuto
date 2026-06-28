'use client';

import { OverseasScanner } from "@/components/OverseasScanner";
import { SwingPredictorCard } from "@/components/SwingPredictorCard";
import { AfterHoursScanner } from "@/components/AfterHoursScanner";
import ManualWatchList from "@/components/ManualWatchList";
import { useState, useCallback, useEffect } from "react";
import { useAuthStore } from "@/store/authStore";
import { useRouter } from "next/navigation";
import type { ScannerTab } from "@/components/ScannerTabs";
import { useWatchlistActions } from "@/hooks/useWatchlistActions";

export default function ScannerPage() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuthStore();
  const [activeTab, setActiveTab] = useState<ScannerTab>("15m");
  const {
    tickers: watchlistTickers,
    addToWatchlist,
  } = useWatchlistActions(isAuthenticated);

  // Auth Guard
  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.push("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  const handleAddToWatchlist = useCallback(async (ticker: string, name: string) => {
    try {
      await addToWatchlist(ticker, name);
    } catch {
      // useWatchlistActions already reports the failure to the user.
    }
  }, [addToWatchlist]);

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
            ) : activeTab === "swing" ? (
              <SwingPredictorCard
                activeTab={activeTab}
                setActiveTab={setActiveTab}
              />
            ) : (
              <AfterHoursScanner
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                onAddToWatchlist={handleAddToWatchlist}
                watchlistTickers={watchlistTickers}
              />
            )}
          </div>
          <div className="lg:col-span-3 min-w-0">
            <div className="sticky top-6 space-y-4">
              <ManualWatchList />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

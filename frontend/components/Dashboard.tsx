"use client";

import { useState } from "react";
import { TradeLogs } from "./TradeLogs";
import { AccountBalance } from "./AccountBalance";
import PortfolioView from "./PortfolioView";
import { AssetTrendChart } from "./AssetTrendChart";
import { LiveTradeTicker } from "./LiveTradeTicker";

import useSWR from "swr";
import { fetcher } from "@/lib/api";

export function Dashboard() {
  const { data: statusData } = useSWR('/bot/status', fetcher, { refreshInterval: 15000 });
  const { data: logsData } = useSWR('/trades/logs', fetcher, { refreshInterval: 15000 });

  const isBotRunning = statusData?.is_running || false;
  const isReal = statusData?.is_real || false;
  const logs = logsData || [];

  const [isChartOpen, setIsChartOpen] = useState(false);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);

  const [displayCurrency, setDisplayCurrency] = useState<"KRW" | "USD">("KRW");

  return (
    <div className={`min-h-screen transition-colors duration-700 ${isReal && isBotRunning ? 'bg-red-950/20' : 'bg-black'}`}>
      <div className="max-w-[1600px] mx-auto p-6 pt-6">
        <LiveTradeTicker latestLog={logs[0]} onClick={() => setIsLogsModalOpen(true)} />

        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-3">
            <span className="bg-indigo-600 w-2.5 h-6 rounded-full"></span>
            기본계좌 현황
          </h1>
          
          <div className="flex items-center gap-3">
            {/* Premium Segmented Control for Currency Selector */}
            <div className="flex bg-zinc-900 border border-zinc-800 p-0.5 rounded-lg shadow-inner">
              <button
                onClick={() => setDisplayCurrency("USD")}
                className={`px-3 py-1 rounded-md text-xs font-bold transition-all duration-300 ${
                  displayCurrency === "USD"
                    ? "bg-zinc-800 text-white shadow"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                $ USD
              </button>
              <button
                onClick={() => setDisplayCurrency("KRW")}
                className={`px-3 py-1 rounded-md text-xs font-bold transition-all duration-300 ${
                  displayCurrency === "KRW"
                    ? "bg-zinc-800 text-white shadow"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                원 KRW
              </button>
            </div>
          </div>
        </div>

        <AccountBalance displayCurrency={displayCurrency} onTotalAssetClick={() => setIsChartOpen(true)} />
        
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-100 mb-4 flex items-center">
            <div className="w-1.5 h-6 bg-blue-500 rounded-full mr-3"></div>
            실시간 포트폴리오 (Portfolio)
          </h2>
          <PortfolioView displayCurrency={displayCurrency} />
        </div>
      </div>

      {/* 프리미엄 다크 글래스모피즘 모달 (자산 성장 차트) */}
      {isChartOpen && (
        <div 
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsChartOpen(false);
          }}
          className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-in fade-in duration-300"
        >
          <div className="bg-zinc-950 border border-zinc-800 rounded-3xl max-w-4xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-300">
            {/* 닫기 버튼 */}
            <button 
              onClick={() => setIsChartOpen(false)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-white p-2 rounded-full hover:bg-zinc-900 active:scale-95 transition-all z-10 font-bold"
              aria-label="닫기"
            >
              ✕
            </button>

            {/* 자산 차트 로드 */}
            <div className="pt-2">
              <AssetTrendChart displayCurrency={displayCurrency} logs={logs} />
            </div>
          </div>
        </div>
      )}

      {/* 프리미엄 다크 글래스모피즘 모달 (전체 거래 내역 상세 조회) */}
      {isLogsModalOpen && (
        <div 
          onClick={(e) => {
            if (e.target === e.currentTarget) setIsLogsModalOpen(false);
          }}
          className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-in fade-in duration-300"
        >
          <div className="bg-zinc-950 border border-zinc-800 rounded-3xl max-w-5xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-300 overflow-hidden max-h-[85vh] flex flex-col">
            {/* 닫기 버튼 */}
            <button 
              onClick={() => setIsLogsModalOpen(false)}
              className="absolute top-4 right-4 text-zinc-500 hover:text-white p-2 rounded-full hover:bg-zinc-900 active:scale-95 transition-all z-10 font-bold"
              aria-label="닫기"
            >
              ✕
            </button>

            {/* 거래 내역 테이블 로드 (단일 팝업 디자인으로 통합) */}
            <div className="flex-1 mt-2">
              <TradeLogs logs={logs} isModalMode={true} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

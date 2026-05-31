"use client";

import { useCallback, useState } from "react";
import { TradeLogs, TradeLog } from "./TradeLogs";
import { AccountBalance } from "./AccountBalance";
import PortfolioView from "./PortfolioView";
import { AssetTrendChart } from "./AssetTrendChart";
import { LiveTradeTicker } from "./LiveTradeTicker";

import { botAPI, tradeAPI, reportAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "sonner";

export function Dashboard() {
  const [isRealEnabled, setIsRealEnabled] = useState(false);
  const [isReal, setIsReal] = useState(false);
  const [logs, setLogs] = useState<TradeLog[]>([]);
  const [isChartOpen, setIsChartOpen] = useState(false);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);
  const [isReportSending, setIsReportSending] = useState(false);

  const handleTriggerManualReport = async () => {
    try {
      setIsReportSending(true);
      await reportAPI.triggerManualReport();
      toast.success("텔레그램 일일 결산 리포트 발송에 성공했습니다.");
    } catch (error) {
      const msg = getErrorMessage(error);
      console.error("Failed to trigger manual report:", msg);
      toast.error(`리포트 발송 실패: ${msg}`);
    } finally {
      setIsReportSending(false);
    }
  };

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await botAPI.getStatus({ signal });
      setIsRealEnabled(res.data.is_real_enabled);
      setIsReal(res.data.is_real);

    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error("Failed to fetch bot status:", msg);
      toast.error(`봇 상태 조회 실패: ${msg}`);
    }
  }, []);

  const fetchLogs = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await tradeAPI.getLogs({ signal });
      setLogs(res.data);
    } catch (error) {
      if (isCancel(error)) return;
      const msg = getErrorMessage(error);
      console.error("Failed to fetch logs:", msg);
      toast.error(`로그 조회 실패: ${msg}`);
    }
  }, []);

  const fetchData = useCallback(async (signal: AbortSignal) => {
    await Promise.all([fetchStatus(signal), fetchLogs(signal)]);
  }, [fetchStatus, fetchLogs]);

  usePolling(fetchData, 5000);

  const handleToggleReal = async () => {
    try {
      await botAPI.toggleReal();
      fetchStatus();
      toast.info("실전 투자 스위치가 변경되었습니다.");
    } catch (error) {
      const msg = getErrorMessage(error);
      console.error("Failed to toggle real switch:", msg);
      toast.error(`스위치 조작 실패: ${msg}`);
    }
  };

  const [displayCurrency, setDisplayCurrency] = useState<"KRW" | "USD">("KRW");

  return (
    <div className={`min-h-screen transition-colors duration-700 ${isReal && isRealEnabled ? 'bg-red-950/20' : 'bg-black'}`}>
      <div className="max-w-[1600px] mx-auto p-6 pt-6">
        {/* 실전 모드(REAL)일 때만 상단 비상 안전 스위치 바를 슬림하게 노출하여 세로 공간 극대화 */}
        {isReal && (
          <div className="mb-6 flex justify-end items-center border-b border-zinc-900 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-zinc-900/50 p-2 rounded-lg border border-zinc-800 backdrop-blur-sm">
                <span className="text-[11px] text-zinc-400 font-semibold">실전투자 안전 스위치</span>
                <button 
                  onClick={handleToggleReal}
                  className={`w-10 h-5 rounded-full p-0.5 transition-colors duration-300 ${isRealEnabled ? 'bg-red-600' : 'bg-zinc-700'}`}
                >
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform duration-300 ${isRealEnabled ? 'translate-x-5' : 'translate-x-0'}`} />
                </button>
              </div>
              {isRealEnabled && (
                <span className="text-[10px] text-red-500 font-extrabold animate-pulse">
                  ⚠️ WARNING: LIVE TRADING ACTIVE
                </span>
              )}
            </div>
          </div>
        )}

        <LiveTradeTicker latestLog={logs[0]} onClick={() => setIsLogsModalOpen(true)} />

        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-3">
            <span className="bg-indigo-600 w-2.5 h-6 rounded-full"></span>
            기본계좌 현황
          </h1>
          
          <div className="flex items-center gap-3">
            {/* 텔레그램 일일 리포트 수동 기동 버튼 */}
            <button
              onClick={handleTriggerManualReport}
              disabled={isReportSending}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all duration-300 border flex items-center gap-1.5 ${
                isReportSending
                  ? "bg-zinc-900 text-zinc-600 border-zinc-800 cursor-not-allowed"
                  : "bg-indigo-950/40 text-indigo-300 border-indigo-900/60 hover:bg-indigo-900/60 hover:text-white active:scale-95 shadow-lg shadow-indigo-950/20"
              }`}
            >
              {isReportSending ? (
                <>
                  <span className="w-1.5 h-1.5 bg-zinc-500 rounded-full animate-ping" />
                  정산 중...
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full" />
                  📨 리포트 즉시 발송
                </>
              )}
            </button>

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

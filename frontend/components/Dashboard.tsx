"use client";

import { useCallback, useState } from "react";
import { BotControl } from "./BotControl";
import { TradeLogs, TradeLog } from "./TradeLogs";
import { AccountBalance } from "./AccountBalance";
import PortfolioView from "./PortfolioView";
import LiveLogViewer from "./LiveLogViewer";

import { botAPI, tradeAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "sonner";

export function Dashboard() {
  const [isRunning, setIsRunning] = useState(false);
  const [isRealEnabled, setIsRealEnabled] = useState(false);
  const [tradeMode, setTradeMode] = useState("VIRTUAL");
  const [isReal, setIsReal] = useState(false);
  const [logs, setLogs] = useState<TradeLog[]>([]);

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await botAPI.getStatus({ signal });
      setIsRunning(res.data.is_running);
      setIsRealEnabled(res.data.is_real_enabled);
      setTradeMode(res.data.trade_mode);
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

  const handleToggle = async () => {
    try {
      if (isRunning) {
        await botAPI.stop();
      } else {
        await botAPI.start();
      }
      fetchStatus();
      toast.success(isRunning ? "봇이 중지되었습니다." : "봇이 가동되었습니다.");
    } catch (error) {
      const msg = getErrorMessage(error);
      console.error("Failed to toggle bot:", msg);
      toast.error(`봇 제어 실패: ${msg}`);
    }
  };

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

  return (
    <div className={`min-h-screen transition-colors duration-700 ${isReal && isRealEnabled ? 'bg-red-950/20' : 'bg-black'}`}>
      <div className="max-w-[1600px] mx-auto p-6 pt-12">
        <header className="mb-10 flex justify-between items-start">
          <div>
            <h1 className={`text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r mb-2 ${isReal && isRealEnabled ? 'from-red-500 to-orange-500' : 'from-blue-400 to-emerald-400'}`}>
              StockAuto Engine
            </h1>
            <div className="flex items-center gap-3">
              <p className="text-zinc-400 font-medium">Automated Algorithmic Trading Dashboard</p>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${isReal ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'}`}>
                {tradeMode} MODE
              </span>
            </div>
          </div>

          {isReal && (
            <div className="flex flex-col items-end gap-2">
              <div className="flex items-center gap-2 bg-zinc-900/50 p-2 rounded-lg border border-zinc-800 backdrop-blur-sm">
                <span className="text-xs text-zinc-400 font-medium">실전투자 안전 스위치</span>
                <button 
                  onClick={handleToggleReal}
                  className={`w-12 h-6 rounded-full p-1 transition-colors duration-300 ${isRealEnabled ? 'bg-red-600' : 'bg-zinc-700'}`}
                >
                  <div className={`w-4 h-4 bg-white rounded-full transition-transform duration-300 ${isRealEnabled ? 'translate-x-6' : 'translate-x-0'}`} />
                </button>
              </div>
              {isRealEnabled && (
                <span className="text-[10px] text-red-500 font-bold animate-pulse">
                  ⚠️ WARNING: LIVE TRADING ACTIVE
                </span>
              )}
            </div>
          )}
        </header>

        <AccountBalance />
        
        <div className="mb-10">
          <h2 className="text-xl font-bold text-slate-100 mb-4 flex items-center">
            <div className="w-1.5 h-6 bg-blue-500 rounded-full mr-3"></div>
            실시간 포트폴리오 (Portfolio)
          </h2>
          <PortfolioView />
        </div>


        <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 mb-20">
          <div className="xl:col-span-1">
            <h2 className="text-xl font-bold text-slate-100 mb-4 flex items-center">
              <div className="w-1.5 h-6 bg-blue-400 rounded-full mr-3"></div>
              컨트롤 패널
            </h2>
            <BotControl isRunning={isRunning} onToggle={handleToggle} />
          </div>
          <div className="xl:col-span-2">
            <h2 className="text-xl font-bold text-slate-100 mb-4 flex items-center">
              <div className="w-1.5 h-6 bg-emerald-500 rounded-full mr-3"></div>
              실시간 봇 활동 상황 (Live Actions)
            </h2>
            <LiveLogViewer />
          </div>
        </div>

        <TradeLogs logs={logs} />
      </div>
    </div>
  );
}

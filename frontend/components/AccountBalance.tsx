"use client";

import React, { useState, useCallback } from "react";
import { Wallet, TrendingUp, DollarSign, PieChart, ShieldAlert, Zap, Crown, Activity } from "lucide-react";
import { cn, reportHandledError } from "@/lib/utils";
import { accountAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";

interface WalletSlot {
  cash: number;
  stock_value: number;
  name?: string;
  weight?: number;
}

interface BalanceData {
  total_asset: number;
  cash_balance: number;
  stock_balance: number;
  profit_rate: number;
  is_mock?: boolean;
  provider?: string;
  profit_loss?: number;
  fx_rate?: number;
  qqq_regime?: "BULLISH" | "BEARISH" | "NEUTRAL";
  wallet_allocation?: Record<string, WalletSlot>;
  focused_radar_tickers?: string[];
}

export function AccountBalance({ 
  displayCurrency = "KRW",
  onTotalAssetClick
}: { 
  displayCurrency?: "KRW" | "USD";
  onTotalAssetClick?: () => void;
}) {
  const [balance, setBalance] = useState<BalanceData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchBalance = useCallback(async (signal?: AbortSignal) => {
    try {
      const res = await accountAPI.getBalance({ signal });
      setBalance(res.data);
      setError(null);
    } catch (err) {
      if (isCancel(err)) return;
      const msg = reportHandledError("Failed to fetch account balance", err);
      setError(msg);
      toast.error(`계좌 정보 갱신 실패: ${msg}`);
    }
  }, []);

  usePolling(fetchBalance, 10000);

  const formatMoney = useCallback((amount: number) => {
    if (!balance) return "";
    if (displayCurrency === "KRW") {
      return `${amount.toLocaleString()}원`;
    } else {
      const usdAmount = balance.fx_rate && balance.fx_rate > 0 
        ? amount / balance.fx_rate 
        : amount / 1350;
      return `$${usdAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
  }, [balance, displayCurrency]);

  if (error) {
    return (
      <div className="bg-rose-500/10 border border-rose-500/20 rounded-2xl p-6 mb-6 flex items-center gap-4 text-rose-500">
        <div className="p-2 bg-rose-500/20 rounded-lg">
          <DollarSign size={20} />
        </div>
        <div>
          <h3 className="font-bold text-sm">계좌 정보를 불러올 수 없습니다</h3>
          <p className="text-xs opacity-80">{error}</p>
        </div>
      </div>
    );
  }

  if (!balance) {
    return (
      <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 mb-6 animate-pulse h-32 flex flex-col justify-center gap-4">
        <div className="h-4 bg-zinc-800 rounded w-1/4"></div>
        <div className="flex gap-4">
          <div className="h-8 bg-zinc-800 rounded w-full"></div>
          <div className="h-8 bg-zinc-800 rounded w-full"></div>
          <div className="h-8 bg-zinc-800 rounded w-full"></div>
          <div className="h-8 bg-zinc-800 rounded w-full"></div>
        </div>
      </div>
    );
  }

  const isProfit = balance.profit_rate >= 0;
  const regime = balance.qqq_regime || "NEUTRAL";

  // 격리형 지갑 동적 분배 리스트 획득 및 폴백 처리
  const walletAllocations = balance.wallet_allocation
    ? Object.entries(balance.wallet_allocation).map(([key, value]) => ({
        key,
        cash: value.cash,
        stock_value: value.stock_value,
        total: value.cash + value.stock_value,
        name: value.name || key.replaceAll("_", " "),
        weight: value.weight || 0.5
      }))
    : [];

  const totalCalculated = walletAllocations.reduce((sum, item) => sum + item.total, 0);
  const denom = totalCalculated > 0 ? totalCalculated : 1;

  return (
    <div className="flex flex-col gap-6 mb-6">
      {/* 4 Core Summary Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Asset (Click to view interactive chart) */}
        <div 
          onClick={onTotalAssetClick}
          className="bg-gradient-to-br from-indigo-900/40 to-purple-900/40 backdrop-blur-md border border-indigo-500/30 hover:border-indigo-500/60 rounded-2xl p-6 shadow-xl relative overflow-hidden transition-all hover:scale-[1.03] cursor-pointer active:scale-[0.98] duration-300 group"
        >
          <div className="absolute top-0 right-0 -mt-4 -mr-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl"></div>
          <div className="flex items-center justify-between mb-2 w-full">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400 group-hover:bg-indigo-500/30 transition-colors">
                <Wallet size={20} className="group-hover:scale-110 transition-transform" />
              </div>
              <div>
                <h3 className="text-zinc-400 font-medium text-sm flex items-center gap-1.5">
                  Total Asset (총 자산)
                  <span className="text-[10px] text-indigo-400 opacity-60 group-hover:opacity-100 transition-opacity font-bold">
                    (차트 📊)
                  </span>
                </h3>
              </div>
            </div>
            <span className={cn(
              "text-[9px] font-bold px-2 py-0.5 rounded-full border tracking-wider uppercase",
              balance.is_mock === false
                ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30 animate-pulse"
                : "bg-amber-500/15 text-amber-400 border-amber-500/30"
            )}>
              {balance.provider || (balance.is_mock === false ? "Live KIS" : "Simulated")}
            </span>
          </div>
          <div className="text-3xl font-extrabold text-white tracking-tight">
            {formatMoney(balance.total_asset)}
          </div>
          {balance.profit_loss !== undefined && (
            <span className={`text-xs font-semibold mt-1.5 flex items-center gap-1 ${
              balance.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}>
              <span>{balance.profit_loss >= 0 ? "▲" : "▼"}</span>
              <span>
                {balance.profit_loss >= 0 ? "+" : "-"}
                {formatMoney(Math.abs(balance.profit_loss))}
              </span>
            </span>
          )}
        </div>

        {/* Profit Rate */}
        <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl transition-transform hover:scale-[1.02] duration-300">
          <div className="flex items-center gap-3 mb-2">
            <div className={cn("p-2 rounded-lg", isProfit ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400")}>
              <TrendingUp size={20} className={cn(!isProfit && "rotate-180")} />
            </div>
            <h3 className="text-zinc-400 font-medium text-sm">Profit Rate (수익률)</h3>
          </div>
          <div className={cn("text-3xl font-extrabold tracking-tight", isProfit ? "text-emerald-400" : "text-rose-400")}>
            {isProfit ? "+" : ""}{balance.profit_rate}%
          </div>
        </div>

        {/* Cash Balance */}
        <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl transition-transform hover:scale-[1.02] duration-300">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
              <DollarSign size={20} />
            </div>
            <h3 className="text-zinc-400 font-medium text-sm">Cash (예수금)</h3>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight mt-1">
            {formatMoney(balance.cash_balance)}
          </div>
        </div>

        {/* Stock Balance */}
        <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl transition-transform hover:scale-[1.02] duration-300">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-amber-500/20 rounded-lg text-amber-400">
              <PieChart size={20} />
            </div>
            <h3 className="text-zinc-400 font-medium text-sm">Stock (주식 평가금)</h3>
          </div>
          <div className="text-2xl font-bold text-white tracking-tight mt-1">
            {formatMoney(balance.stock_balance)}
          </div>
        </div>
      </div>

      {/* 2-Slot Isolated Portfolio & Regime Traffic Sluice Unified Dashboard */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 relative z-10">
        
        {/* Left: 격리형 2슬롯 통합 자산 원장 (col-span-2) */}
        <div className="lg:col-span-2 bg-[#090d16]/70 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl relative overflow-hidden flex flex-col justify-between">
          {/* Glow Accents */}
          <div className="absolute top-0 right-0 -mt-12 -mr-12 w-48 h-48 bg-indigo-500/5 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 -mb-12 -ml-12 w-48 h-48 bg-emerald-500/5 rounded-full blur-3xl"></div>

          <div className="relative z-10 space-y-6">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-4 border-b border-zinc-800/60">
              <div>
                <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-2.5">
                  <ShieldAlert size={20} className="text-indigo-400" />
                  {walletAllocations.length === 1 
                    ? `${walletAllocations[0].name} 실시간 자산 원장 (Strategy Asset Ledger)` 
                    : "전략 격리 통합 자산 원장 (Unified Strategy Asset Ledger)"}
                </h3>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  {walletAllocations.length === 1 
                    ? `가동 중인 ${walletAllocations[0].name} 전략의 실시간 예수금 및 주식 평가 지분 비율을 모니터링하는 자산 원장입니다.` 
                    : "대결에 가동 중인 각 전략의 실시간 예수금 및 주식 평가 지분 비율을 감시하는 자산 원장입니다."}
                </p>
              </div>
            </div>

            {/* 📊 계좌 통합 자산 배분 게이지 (단일 100% 막대) */}
            <div className="bg-zinc-950/70 border border-zinc-800/50 rounded-2xl p-5 shadow-inner">
              <div className="flex justify-between items-center mb-3">
                <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500">
                  Total Capital Allocation Gauge (통합 자산 지분 게이지)
                </span>
                <span className="text-[10px] text-zinc-400 font-bold font-mono">
                  총 자산 평가: {formatMoney(balance.total_asset)}
                </span>
              </div>
              
              {/* Dynamic Segments Progress Bar */}
              <div className="h-4 bg-zinc-900/60 rounded-full overflow-hidden flex shadow-inner border border-zinc-800/50 relative">
                {walletAllocations.map((item, idx) => {
                  const stockPct = (item.stock_value / denom) * 100;
                  const cashPct = (item.cash / denom) * 100;
                  
                  // Dynamic HSL colors for up to 5 strategies
                  const colors = [
                    { stock: "from-emerald-600 to-emerald-500", cash: "from-blue-600 to-blue-500" },
                    { stock: "from-purple-600 to-purple-500", cash: "from-indigo-750 to-indigo-650" },
                    { stock: "from-amber-600 to-amber-500", cash: "from-yellow-700 to-yellow-600" },
                    { stock: "from-rose-600 to-rose-500", cash: "from-pink-700 to-pink-600" },
                    { stock: "from-cyan-600 to-cyan-500", cash: "from-teal-700 to-teal-600" }
                  ];
                  const color = colors[idx % colors.length];
                  
                  return (
                    <React.Fragment key={item.key}>
                      {stockPct > 0 && (
                        <div 
                          className={cn("h-full bg-gradient-to-r transition-all duration-500 shrink-0", color.stock)}
                          style={{ width: `${stockPct}%` }}
                          title={`${item.name} 주식: ${formatMoney(item.stock_value)} (${stockPct.toFixed(1)}%)`}
                        />
                      )}
                      {cashPct > 0 && (
                        <div 
                          className={cn(
                            "h-full bg-gradient-to-r transition-all duration-500 shrink-0", 
                            (item.key === "regime_switching" && regime !== "BULLISH") ? "bg-zinc-800" : color.cash
                          )}
                          style={{ width: `${cashPct}%` }}
                          title={item.key === "regime_switching" && regime !== "BULLISH"
                            ? `${item.name} 격리현금 보호: ${formatMoney(item.cash)} (${cashPct.toFixed(1)}%)`
                            : `${item.name} 예수금: ${formatMoney(item.cash)} (${cashPct.toFixed(1)}%)`
                          }
                        />
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
              
              {/* Legend Grid */}
              <div className="flex flex-wrap gap-x-4 gap-y-2 mt-4 text-[10px] font-bold text-zinc-400">
                {walletAllocations.map((item, idx) => {
                  const colors = [
                    { stock: "bg-emerald-500 shadow-[0_0_6px_#10b981]", cash: "bg-blue-500 shadow-[0_0_6px_#3b82f6]" },
                    { stock: "bg-purple-500 shadow-[0_0_6px_#a855f7]", cash: "bg-indigo-500 shadow-[0_0_6px_#6366f1]" },
                    { stock: "bg-amber-500 shadow-[0_0_6px_#f59e0b]", cash: "bg-yellow-500 shadow-[0_0_6px_#eab308]" },
                    { stock: "bg-rose-500 shadow-[0_0_6px_#f43f5e]", cash: "bg-pink-500 shadow-[0_0_6px_#ec4899]" },
                    { stock: "bg-cyan-500 shadow-[0_0_6px_#06b6d4]", cash: "bg-teal-500 shadow-[0_0_6px_#14b8a6]" }
                  ];
                  const color = colors[idx % colors.length];
                  const stockPct = (item.stock_value / denom) * 100;
                  const cashPct = (item.cash / denom) * 100;
                  
                  return (
                    <React.Fragment key={item.key}>
                      <div className="flex items-center gap-1.5">
                        <span className={cn("w-2 h-2 rounded-full", color.stock)} />
                        <span>{item.name} 주식 ({stockPct.toFixed(1)}%)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className={cn(
                          "w-2 h-2 rounded-full", 
                          (item.key === "regime_switching" && regime !== "BULLISH") ? "bg-zinc-750" : color.cash
                        )} />
                        <span>
                          {item.key === "regime_switching" && regime !== "BULLISH"
                            ? `${item.name} 격리현금`
                            : `${item.name} 예수금`
                          } ({cashPct.toFixed(1)}%)
                        </span>
                      </div>
                    </React.Fragment>
                  );
                })}
              </div>
            </div>

            {/* 듀얼/단일 슬롯 전략 비교 카드 그리드 */}
            <div className={cn(
              "grid gap-5",
              walletAllocations.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2"
            )}>
              {walletAllocations.map((item, idx) => {
                const total = item.cash + item.stock_value;
                const internalCashPct = total > 0 ? (item.cash / total) * 100 : 100;
                const internalStockPct = total > 0 ? (item.stock_value / total) * 100 : 0;
                
                // Color variants for cards
                const cardColors = [
                  { border: "hover:border-emerald-500/20", iconBg: "bg-emerald-500/10 text-emerald-400", progress: "bg-emerald-500/90 shadow-[0_0_10px_#10b981]" },
                  { border: "hover:border-purple-500/20", iconBg: "bg-purple-500/10 text-purple-400", progress: "bg-purple-500/90 shadow-[0_0_10px_#a855f7]" },
                  { border: "hover:border-amber-500/20", iconBg: "bg-amber-500/10 text-amber-400", progress: "bg-amber-500/90 shadow-[0_0_10px_#f59e0b]" },
                  { border: "hover:border-rose-500/20", iconBg: "bg-rose-500/10 text-rose-400", progress: "bg-rose-500/90 shadow-[0_0_10px_#f43f5e]" },
                  { border: "hover:border-cyan-500/20", iconBg: "bg-cyan-500/10 text-cyan-400", progress: "bg-cyan-500/90 shadow-[0_0_10px_#06b6d4]" }
                ];
                const cardColor = cardColors[idx % cardColors.length];
                const textHighlight = idx === 0 ? "text-emerald-400" : "text-purple-400";
                
                return (
                  <div key={item.key} className={cn(
                    "bg-zinc-900/30 border border-zinc-800/80 transition-all duration-300 rounded-2xl p-5 flex flex-col justify-between group",
                    cardColor.border
                  )}>
                    <div>
                      <div className="flex justify-between items-start mb-3">
                        <div className="flex items-center gap-2">
                          <div className={cn("p-1.5 rounded-lg group-hover:scale-110 transition-transform", cardColor.iconBg)}>
                            {item.key === "regime_switching" ? <Crown size={16} /> : <Zap size={16} />}
                          </div>
                          <div>
                            <h4 className="text-sm font-bold text-white tracking-tight">{item.name}</h4>
                            <p className="text-[10px] text-zinc-500">{item.key.toUpperCase()} PORTFOLIO</p>
                          </div>
                        </div>
                        <div className="relative group/tooltip cursor-help">
                          <span className={cn(
                            "text-[9px] font-extrabold px-1.5 py-0.5 rounded border uppercase tracking-wide",
                            (item.key === "regime_switching" && regime !== "BULLISH")
                              ? "bg-amber-500/15 text-amber-400 border-amber-500/20"
                              : "bg-emerald-500/15 text-emerald-400 border-emerald-500/20 animate-pulse"
                          )}>
                            {(item.key === "regime_switching" && regime !== "BULLISH") ? "격리중 🛡️" : "가동중 ℹ️"}
                          </span>
                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 bg-zinc-950 border border-zinc-800 text-[10px] text-zinc-300 rounded-xl opacity-0 pointer-events-none group-hover/tooltip:opacity-100 transition-opacity duration-200 z-50 shadow-2xl leading-normal text-left font-normal normal-case">
                            {item.key === "regime_switching" && regime !== "BULLISH"
                              ? "상승장이 아닐 때는 리스크 보호를 위해 봇 매수를 차단하고 지분 자산을 100% 현금 상태로 금고에 안전하게 격리 보호 중입니다."
                              : `계좌 총 자산의 ${(item.weight * 100).toFixed(0)}% 비중을 할당받아 ${item.name} 전략에 입각하여 안전하게 실시간 기동 중입니다.`}
                          </div>
                        </div>
                      </div>
                      
                      <div className="space-y-3 mt-4">
                        <div>
                          <div className="flex justify-between text-xs text-zinc-400 mb-1">
                            <span>가용 예수금 (Cash)</span>
                            <span className="font-bold text-white">{formatMoney(item.cash)}</span>
                          </div>
                          <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-blue-500/90 shadow-[0_0_10px_#3b82f6] transition-all duration-500" 
                              style={{ width: `${internalCashPct}%` }}
                            />
                          </div>
                        </div>
                        
                        <div>
                          <div className="flex justify-between text-xs text-zinc-400 mb-1">
                            <span>주식 평가금 (Stock)</span>
                            <span className="font-bold text-white">{formatMoney(item.stock_value)}</span>
                          </div>
                          <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                            <div 
                              className={cn("h-full transition-all duration-500", cardColor.progress)}
                              style={{ width: `${internalStockPct}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    <div className="mt-4 pt-3 border-t border-zinc-800/50 flex justify-between items-center text-xs">
                      <span className="text-zinc-500 font-medium flex items-center gap-1">
                        전략 총자산 (지분 {(item.weight * 100).toFixed(0)}%)
                        {item.key === "regime_switching" && regime !== "BULLISH" && (
                          <span className="text-amber-500 text-[8px] font-black bg-amber-500/10 px-1 rounded border border-amber-500/20">🛡️ 100% 현금 격리</span>
                        )}
                      </span>
                      <span className={cn("font-black", textHighlight)}>{formatMoney(total)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right: QQQ 관제탑 (col-span-1) */}
        <div className="bg-[#090d16]/70 backdrop-blur-xl border border-zinc-800/80 rounded-3xl p-6 shadow-2xl relative overflow-hidden flex flex-col justify-between min-h-[360px]">
          {/* Glow Accents */}
          <div className="absolute top-0 right-0 -mt-12 -mr-12 w-48 h-48 bg-blue-500/5 rounded-full blur-3xl"></div>
          <div className="absolute bottom-0 left-0 -mb-12 -ml-12 w-48 h-48 bg-indigo-500/5 rounded-full blur-3xl"></div>
          
          <div className="relative z-10 flex flex-col h-full justify-between gap-6">
            <div>
              <h3 className="text-base font-extrabold text-white tracking-tight flex items-center gap-2 border-b border-zinc-800/60 pb-4">
                <Activity className="text-blue-400 animate-pulse" size={18} />
                QQQ 레짐 관제탑 (Sluice Controller)
              </h3>
              <p className="text-[11px] text-zinc-400 mt-3 leading-relaxed">
                나스닥 100 지수의 실시간 추세를 체크하여 각 격리 슬롯의 자금 가동 한도를 동적으로 통제하고 제어하는 시스템 핵심 관제탑입니다.
              </p>
            </div>
            
            {/* Pulsing Light Center */}
            <div className="bg-zinc-950/80 border border-zinc-850/80 rounded-2xl p-5 flex flex-col items-center justify-center relative overflow-hidden py-8 shadow-inner">
              <h4 className="text-[10px] font-bold text-zinc-500 mb-4 tracking-wider uppercase flex items-center gap-1.5">
                <Activity size={10} className="text-zinc-650 animate-pulse" />
                QQQ Sluice Signal
              </h4>
              
              <div className="flex gap-4 items-center bg-zinc-900/60 px-5 py-3 rounded-full border border-zinc-800 shadow-2xl">
                {/* RED (BEARISH) Light */}
                <div className="relative">
                  <div className={cn(
                    "w-6 h-6 rounded-full transition-all duration-500",
                    regime === "BEARISH" 
                      ? "bg-rose-500 shadow-[0_0_15px_#f43f5e]" 
                      : "bg-zinc-800 opacity-20"
                  )} />
                  {regime === "BEARISH" && (
                    <span className="absolute inset-0 rounded-full bg-rose-500/40 animate-ping opacity-75" />
                  )}
                </div>
                
                {/* YELLOW (NEUTRAL) Light */}
                <div className="relative">
                  <div className={cn(
                    "w-6 h-6 rounded-full transition-all duration-500",
                    regime === "NEUTRAL" 
                      ? "bg-amber-500 shadow-[0_0_15px_#f59e0b]" 
                      : "bg-zinc-800 opacity-20"
                  )} />
                  {regime === "NEUTRAL" && (
                    <span className="absolute inset-0 rounded-full bg-amber-500/40 animate-ping opacity-75" />
                  )}
                </div>
                
                {/* GREEN (BULLISH) Light */}
                <div className="relative">
                  <div className={cn(
                    "w-6 h-6 rounded-full transition-all duration-500",
                    regime === "BULLISH" 
                      ? "bg-emerald-500 shadow-[0_0_15px_#10b981]" 
                      : "bg-zinc-800 opacity-20"
                  )} />
                  {regime === "BULLISH" && (
                    <span className="absolute inset-0 rounded-full bg-emerald-500/40 animate-ping opacity-75" />
                  )}
                </div>
              </div>
              
              <div className="mt-4 text-center">
                <span className={cn(
                  "text-xs font-black tracking-tight",
                  regime === "BULLISH" ? "text-emerald-400" :
                  regime === "NEUTRAL" ? "text-amber-400" : "text-rose-400"
                )}>
                  {regime === "BULLISH" ? "▲ 상승국면 (BULLISH)" :
                   regime === "NEUTRAL" ? "■ 조정국면 (NEUTRAL)" : "▼ 하락국면 (BEARISH)"}
                </span>
                <p className="text-[9px] text-zinc-500 mt-1 font-semibold leading-relaxed max-w-[170px]">
                  {regime === "BULLISH" ? "상승추세 가시화로 두 슬롯 모두 적극 가동중 (EP 50% | RS 50%)" :
                   regime === "NEUTRAL" ? "횡보로 인한 리스크 차단을 위해 RS 50% 현금 격리 보존 모드 가동" : 
                   "하락세 심화로 위기 감지. RS 50% 현금 완벽 피난 격리 및 EP 단독 방어"}
                </p>
              </div>
            </div>
            
            <div className="bg-zinc-900/30 rounded-2xl border border-zinc-800/40 p-4 space-y-1.5">
              <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-wider block">관제탑 제어 규칙</span>
              <p className="text-[9px] text-zinc-500 leading-relaxed leading-normal">
                QQQ 이평 배열을 상시 진단하며, 하락장 진입 시 RS 슬롯의 가동 한도를 즉각 0% 차단 격리함으로써 계좌 파산 리스크를 기계적으로 차단합니다.
              </p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

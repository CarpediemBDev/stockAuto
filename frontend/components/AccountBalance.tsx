"use client";

import React, { useState, useCallback } from "react";
import { Wallet, TrendingUp, DollarSign, PieChart, ShieldAlert, Zap, Crown, Activity } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { accountAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";

interface WalletSlot {
  cash: number;
  stock_value: number;
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
  wallet_allocation?: {
    episodic_pivot: WalletSlot;
    regime_switching: WalletSlot;
  };
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
      const msg = getErrorMessage(err);
      console.error("Failed to fetch account balance:", msg);
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

  // 격리형 지갑 기본 분배 폴백 처리
  const defaultWalletAlloc = {
    episodic_pivot: { cash: balance.cash_balance * 0.5, stock_value: balance.stock_balance * 0.5 },
    regime_switching: { cash: balance.cash_balance * 0.5, stock_value: balance.stock_balance * 0.5 }
  };
  const epAllocation = balance.wallet_allocation?.episodic_pivot || defaultWalletAlloc.episodic_pivot;
  const rsAllocation = balance.wallet_allocation?.regime_switching || defaultWalletAlloc.regime_switching;

  const epTotal = epAllocation.cash + epAllocation.stock_value;
  const epCashPct = epTotal > 0 ? (epAllocation.cash / epTotal) * 100 : 100;
  const epStockPct = epTotal > 0 ? (epAllocation.stock_value / epTotal) * 100 : 0;

  const rsTotal = rsAllocation.cash + rsAllocation.stock_value;
  const rsCashPct = rsTotal > 0 ? (rsAllocation.cash / rsTotal) * 100 : 100;
  const rsStockPct = rsTotal > 0 ? (rsAllocation.stock_value / rsTotal) * 100 : 0;

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

      {/* 2-Slot Isolated Portfolio & Regime Traffic Sluice Dashboard */}
      <div className="bg-zinc-950/40 backdrop-blur-md border border-zinc-800/80 rounded-3xl p-6 shadow-2xl relative overflow-hidden">
        {/* Glow Accents */}
        <div className="absolute top-0 right-0 -mt-10 -mr-10 w-40 h-40 bg-indigo-500/5 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 -mb-10 -ml-10 w-40 h-40 bg-emerald-500/5 rounded-full blur-3xl"></div>

        <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-6 pb-4 border-b border-zinc-800/60">
          <div>
            <h3 className="text-lg font-black text-white tracking-tight flex items-center gap-2">
              <ShieldAlert size={20} className="text-indigo-400" />
              격리형 2슬롯 자산 고밀도 분배 정보 (Isolated Slot Wallet Allocations)
            </h3>
            <p className="text-xs text-zinc-500 mt-0.5">단일 계좌 내에서 수학적으로 안전하게 격리 가동되는 두 핵심 알고리즘의 자금 현황입니다.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 1. EP Slot */}
          <div className="bg-zinc-900/40 border border-zinc-800/80 hover:border-emerald-500/20 transition-all duration-300 rounded-2xl p-5 flex flex-col justify-between group">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-emerald-500/10 rounded-lg text-emerald-400 group-hover:scale-110 transition-transform">
                    <Zap size={16} className="animate-pulse" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white tracking-tight">EP 에피소딕 피벗 슬롯</h4>
                    <p className="text-[10px] text-zinc-500">Episodic Pivot Strategy</p>
                  </div>
                </div>
                <div className="relative group/tooltip cursor-help">
                  <span className="text-[9px] font-extrabold px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 uppercase tracking-wide">
                    비중 50% 격리중 ℹ️
                  </span>
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 bg-zinc-950 border border-zinc-800 text-[10px] text-zinc-300 rounded-xl opacity-0 pointer-events-none group-hover/tooltip:opacity-100 transition-opacity duration-200 z-50 shadow-2xl leading-normal text-left font-normal normal-case">
                    총 자산의 50% 자금을 독점 분배받아 개별 변동성 돌파 매매전략(EP) 전용으로 격리 운용하며, 나머지 50% 비중은 RS 슬롯에 할당됩니다.
                  </div>
                </div>
              </div>
              
              <div className="space-y-3 mt-4">
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>가용 예수금 (Cash)</span>
                    <span className="font-bold text-white">{formatMoney(epAllocation.cash)}</span>
                  </div>
                  <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-blue-500/90 shadow-[0_0_10px_#3b82f6] transition-all duration-500" 
                      style={{ width: `${epCashPct}%` }}
                    />
                  </div>
                </div>
                
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>주식 평가금 (Stock)</span>
                    <span className="font-bold text-white">{formatMoney(epAllocation.stock_value)}</span>
                  </div>
                  <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-emerald-500/90 shadow-[0_0_10px_#10b981] transition-all duration-500" 
                      style={{ width: `${epStockPct}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
            
            <div className="mt-4 pt-3 border-t border-zinc-800/50 flex justify-between items-center text-xs">
              <span className="text-zinc-500 font-medium">EP 슬롯 총자산</span>
              <span className="font-black text-emerald-400">{formatMoney(epTotal)}</span>
            </div>
          </div>

          {/* 2. QQQ Market Regime Sluice Center Light */}
          <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-2xl p-5 flex flex-col items-center justify-center relative overflow-hidden group">
            <h4 className="text-xs font-bold text-zinc-400 mb-4 tracking-wider uppercase flex items-center gap-1.5">
              <Activity size={12} className="text-zinc-500 animate-pulse" />
              QQQ Regime Sluice
            </h4>
            
            <div className="flex gap-4 items-center bg-zinc-950 px-5 py-3.5 rounded-full border border-zinc-800/80 shadow-2xl">
              {/* RED (BEARISH) Light */}
              <div className="relative">
                <div className={cn(
                  "w-7 h-7 rounded-full transition-all duration-500",
                  regime === "BEARISH" 
                    ? "bg-rose-500 shadow-[0_0_20px_#f43f5e]" 
                    : "bg-zinc-800 opacity-20"
                )} />
                {regime === "BEARISH" && (
                  <span className="absolute inset-0 rounded-full bg-rose-500/40 animate-ping opacity-75" />
                )}
              </div>
              
              {/* YELLOW (NEUTRAL) Light */}
              <div className="relative">
                <div className={cn(
                  "w-7 h-7 rounded-full transition-all duration-500",
                  regime === "NEUTRAL" 
                    ? "bg-amber-500 shadow-[0_0_20px_#f59e0b]" 
                    : "bg-zinc-800 opacity-20"
                )} />
                {regime === "NEUTRAL" && (
                  <span className="absolute inset-0 rounded-full bg-amber-500/40 animate-ping opacity-75" />
                )}
              </div>
              
              {/* GREEN (BULLISH) Light */}
              <div className="relative">
                <div className={cn(
                  "w-7 h-7 rounded-full transition-all duration-500",
                  regime === "BULLISH" 
                    ? "bg-emerald-500 shadow-[0_0_20px_#10b981]" 
                    : "bg-zinc-800 opacity-20"
                )} />
                {regime === "BULLISH" && (
                  <span className="absolute inset-0 rounded-full bg-emerald-500/40 animate-ping opacity-75" />
                )}
              </div>
            </div>
            
            <div className="mt-4 text-center">
              <span className={cn(
                "text-sm font-black tracking-tight",
                regime === "BULLISH" ? "text-emerald-400" :
                regime === "NEUTRAL" ? "text-amber-400" : "text-rose-400"
              )}>
                {regime === "BULLISH" ? "▲ 상승국면 (BULLISH)" :
                 regime === "NEUTRAL" ? "■ 조정국면 (NEUTRAL)" : "▼ 하락국면 (BEARISH)"}
              </span>
              <p className="text-[10px] text-zinc-500 mt-1 font-medium leading-relaxed max-w-[200px]">
                {regime === "BULLISH" ? "레짐스위칭 V2 활성화 완료 (대국면 편승 극대화)" :
                 regime === "NEUTRAL" ? "레짐 V2 현금 100% 긴급 격리 (EP만 방어기동)" : 
                 "레짐 V2 차단장치 작동 (현금 100% 완벽 보호)"}
              </p>
            </div>
          </div>

          {/* 3. RS Slot */}
          <div className="bg-zinc-900/40 border border-zinc-800/80 hover:border-purple-500/20 transition-all duration-300 rounded-2xl p-5 flex flex-col justify-between group">
            <div>
              <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-purple-500/10 rounded-lg text-purple-400 group-hover:scale-110 transition-transform">
                    <Crown size={16} />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-white tracking-tight">RS 마스터 레짐스위칭 V2</h4>
                    <p className="text-[10px] text-zinc-500">Regime Switching Strategy</p>
                  </div>
                </div>
                <div className="relative group/tooltip cursor-help">
                  <span className={cn(
                    "text-[9px] font-extrabold px-1.5 py-0.5 rounded border uppercase tracking-wide",
                    regime === "BULLISH" 
                      ? "bg-purple-500/15 text-purple-400 border-purple-500/20" 
                      : "bg-zinc-800 text-zinc-500 border-zinc-700/30"
                  )}>
                    {regime === "BULLISH" ? "비중 50% 가동중 ℹ️" : "비중 50% 차단됨 ℹ️"}
                  </span>
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 bg-zinc-950 border border-zinc-800 text-[10px] text-zinc-300 rounded-xl opacity-0 pointer-events-none group-hover/tooltip:opacity-100 transition-opacity duration-200 z-50 shadow-2xl leading-normal text-left font-normal normal-case">
                    {regime === "BULLISH" 
                      ? "총 자산의 50% 자금을 할당받아 상승장 전용 불타기 피라미딩 전략(RS V2)을 적극 가동 중입니다."
                      : "상승장이 아닐 때는 손실 방지를 위해 자금 가동을 차단하고 100% 현금을 보존하며, 나머지 50% 비중은 EP 슬롯에서 단독 가동됩니다."}
                  </div>
                </div>
              </div>
              
              <div className="space-y-3 mt-4">
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>가용 예수금 (Cash)</span>
                    <span className="font-bold text-white">{formatMoney(rsAllocation.cash)}</span>
                  </div>
                  <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-blue-500/90 shadow-[0_0_10px_#3b82f6] transition-all duration-500" 
                      style={{ width: `${rsCashPct}%` }}
                    />
                  </div>
                </div>
                
                <div>
                  <div className="flex justify-between text-xs text-zinc-400 mb-1">
                    <span>주식 평가금 (Stock)</span>
                    <span className="font-bold text-white">{formatMoney(rsAllocation.stock_value)}</span>
                  </div>
                  <div className="h-2 bg-zinc-800/60 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-purple-500/90 shadow-[0_0_10px_#a855f7] transition-all duration-500" 
                      style={{ width: `${rsStockPct}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>
            
            <div className="mt-4 pt-3 border-t border-zinc-800/50 flex justify-between items-center text-xs">
              <span className="text-zinc-500 font-medium flex items-center gap-1">
                RS 슬롯 총자산
                {regime !== "BULLISH" && (
                  <span className="text-amber-500 text-[8px] font-black bg-amber-500/10 px-1 rounded border border-amber-500/20">🛡️ 100% 현금 대피</span>
                )}
              </span>
              <span className="font-black text-purple-400">{formatMoney(rsTotal)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

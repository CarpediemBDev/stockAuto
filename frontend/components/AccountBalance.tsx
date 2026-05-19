"use client";

import React, { useState, useCallback } from "react";
import { Wallet, TrendingUp, DollarSign, PieChart } from "lucide-react";
import { cn, getErrorMessage } from "@/lib/utils";
import { accountAPI, isCancel } from "@/lib/api";
import { usePolling } from "@/hooks/usePolling";
import { toast } from "sonner";

interface BalanceData {
  total_asset: number;
  cash_balance: number;
  stock_balance: number;
  profit_rate: number;
  is_mock?: boolean;
  provider?: string;
  profit_loss?: number;
  fx_rate?: number;
}

export function AccountBalance({ displayCurrency = "KRW" }: { displayCurrency?: "KRW" | "USD" }) {
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Total Asset */}
      <div className="bg-gradient-to-br from-indigo-900/40 to-purple-900/40 backdrop-blur-md border border-indigo-500/20 rounded-2xl p-6 shadow-xl relative overflow-hidden transition-transform hover:scale-[1.02] duration-300">
        <div className="absolute top-0 right-0 -mt-4 -mr-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl"></div>
        <div className="flex items-center justify-between mb-2 w-full">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
              <Wallet size={20} />
            </div>
            <h3 className="text-zinc-400 font-medium text-sm">Total Asset (총 자산)</h3>
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
          {displayCurrency === "KRW"
            ? `${balance.total_asset.toLocaleString()}원`
            : `$${(balance.fx_rate && balance.fx_rate > 0
                ? balance.total_asset / balance.fx_rate
                : balance.total_asset / 1350).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          }
        </div>
        {balance.profit_loss !== undefined && (
          <span className={`text-xs font-semibold mt-1.5 flex items-center gap-1 ${
            balance.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"
          }`}>
            <span>{balance.profit_loss >= 0 ? "▲" : "▼"}</span>
            <span>
              {displayCurrency === "KRW"
                ? `${balance.profit_loss >= 0 ? "+" : "-"}${Math.abs(balance.profit_loss).toLocaleString()}원`
                : `${balance.profit_loss >= 0 ? "+" : "-"}$${(balance.fx_rate && balance.fx_rate > 0
                    ? Math.abs(balance.profit_loss) / balance.fx_rate
                    : Math.abs(balance.profit_loss) / 1350).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              }
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
          {displayCurrency === "KRW"
            ? `${balance.cash_balance.toLocaleString()}원`
            : `$${(balance.fx_rate && balance.fx_rate > 0
                ? balance.cash_balance / balance.fx_rate
                : balance.cash_balance / 1350).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          }
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
          {displayCurrency === "KRW"
            ? `${balance.stock_balance.toLocaleString()}원`
            : `$${(balance.fx_rate && balance.fx_rate > 0
                ? balance.stock_balance / balance.fx_rate
                : balance.stock_balance / 1350).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
          }
        </div>
      </div>
    </div>
  );
}

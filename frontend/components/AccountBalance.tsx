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
}

export function AccountBalance() {
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
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-indigo-500/20 rounded-lg text-indigo-400">
            <Wallet size={20} />
          </div>
          <h3 className="text-zinc-400 font-medium text-sm">Total Asset (총 자산)</h3>
        </div>
        <div className="text-3xl font-extrabold text-white tracking-tight">
          ₩{balance.total_asset.toLocaleString()}
        </div>
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
          ₩{balance.cash_balance.toLocaleString()}
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
          ₩{balance.stock_balance.toLocaleString()}
        </div>
      </div>
    </div>
  );
}

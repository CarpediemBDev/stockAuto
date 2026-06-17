"use client";

import React, { useEffect, useState } from "react";
import { TradeLog } from "./TradeLogs";
import { cn } from "@/lib/utils";
import { useTimezone } from "@/store/timezoneStore";

interface LiveTradeTickerProps {
  latestLog?: TradeLog;
  onClick?: () => void;
}

export function LiveTradeTicker({ latestLog, onClick }: LiveTradeTickerProps) {
  const [timeAgo, setTimeAgo] = useState<string>("");
  const { selectedTimezone } = useTimezone();

  useEffect(() => {
    if (!latestLog) return;

    const updateTime = () => {
      const date = new Date(latestLog.executed_at);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);

      if (diffMins < 1) {
        setTimeAgo("방금 전");
      } else if (diffMins < 60) {
        setTimeAgo(`${diffMins}분 전`);
      } else {
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) {
          setTimeAgo(`${diffHours}시간 전`);
        } else {
          setTimeAgo(date.toLocaleDateString());
        }
      }
    };

    updateTime();
  }, [latestLog]);

  if (!latestLog) {
    return (
      <div className="w-full bg-zinc-950/40 backdrop-blur-md border border-zinc-900 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs text-zinc-500 mb-6 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
          </span>
          <span className="font-medium tracking-tight">📡 자율 트레이딩 엔진이 작동 중이며, 실시간 글로벌 마켓을 감시하고 있습니다...</span>
        </div>
        <span className="text-[10px] text-zinc-600 font-mono select-none">SYSTEM MONITOR ACTIVE</span>
      </div>
    );
  }

  const isBuy = latestLog.trade_type === "BUY";
  const hasPnL = latestLog.realized_pnl !== undefined && latestLog.realized_pnl !== null;
  const pnl = hasPnL ? latestLog.realized_pnl! : 0;
  const rate = hasPnL ? latestLog.return_rate! : 0;
  const isProfit = pnl >= 0;

  const timeString = new Date(latestLog.executed_at).toLocaleTimeString('ko-KR', {
    timeZone: selectedTimezone.timeZone,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div 
      onClick={onClick}
      className="w-full bg-zinc-950/60 backdrop-blur-md border border-zinc-800/80 rounded-xl p-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 mb-6 shadow-lg animate-in fade-in slide-in-from-top-2 duration-300 cursor-pointer hover:bg-zinc-900/60 hover:border-zinc-700/80 active:scale-[0.99] transition-all group"
      title="클릭하여 전체 거래 내역 보기"
    >
      {/* 왼쪽: 라이브 상태 표시 및 최근 활동 요약 */}
      <div className="flex items-center gap-3">
        <span className="relative flex h-2.5 w-2.5 shrink-0">
          <span className={cn(
            "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
            isBuy ? "bg-emerald-400" : "bg-rose-400"
          )}></span>
          <span className={cn(
            "relative inline-flex rounded-full h-2.5 w-2.5",
            isBuy ? "bg-emerald-500" : "bg-rose-500"
          )}></span>
        </span>
        
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="text-zinc-500 font-bold">LATEST TRADE</span>
          <span className="text-zinc-600">•</span>
          
          <span className={cn(
            "px-1.5 py-0.5 rounded text-[10px] font-black tracking-wider uppercase border",
            isBuy 
              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" 
              : "bg-rose-500/10 text-rose-400 border-rose-500/20"
          )}>
            {isBuy ? "BUY" : "SELL"}
          </span>
          
          <span className="font-semibold text-white">
            {latestLog.ticker_name || latestLog.ticker}
          </span>
          <span className="text-zinc-500 font-mono text-[10px] bg-zinc-900 border border-zinc-800/60 px-1 py-0.25 rounded">
            {latestLog.ticker}
          </span>

          <span className="text-zinc-400">
            <span className="font-mono text-zinc-300 font-bold">{latestLog.quantity}주</span> 체결 완료
          </span>

          <span className="text-zinc-500 font-mono text-[11px] font-semibold">
            (@ ${latestLog.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })})
          </span>

          {/* 매도 실현 손익 정보 */}
          {!isBuy && hasPnL && (
            <>
              <span className="text-zinc-600 font-extrabold shrink-0">|</span>
              <span className={cn(
                "font-bold flex items-center gap-0.5",
                isProfit ? "text-emerald-400" : "text-rose-400"
              )}>
                실수익률 {isProfit ? "▲" : "▼"} {Math.abs(rate).toFixed(2)}%
              </span>
              <span className={cn(
                "font-mono font-black",
                isProfit ? "text-emerald-400" : "text-rose-400"
              )}>
                ({isProfit ? "+" : "-"}${Math.abs(pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })})
              </span>
            </>
          )}
        </div>
      </div>

      {/* 오른쪽: 체결 시간 & 상세보기 배지 */}
      <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono shrink-0 sm:self-center">
        <span className="bg-zinc-900/80 px-2 py-0.5 rounded border border-zinc-800/50 text-zinc-400 font-semibold">{selectedTimezone.abbr}</span>
        <span>{timeString}</span>
        <span className="text-zinc-700 font-extrabold">•</span>
        <span className="bg-zinc-900/80 px-2 py-0.5 rounded border border-zinc-800/50 text-zinc-400 font-semibold">{timeAgo}</span>
        <span className="text-zinc-700 font-extrabold shrink-0">•</span>
        <span className="bg-indigo-950/40 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded font-sans font-bold group-hover:bg-indigo-600 group-hover:text-white transition-all duration-200">🔍 상세보기</span>
      </div>
    </div>
  );
}

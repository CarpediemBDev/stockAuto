"use client";

import { useTimezone } from "@/store/timezoneStore";

export interface TradeLog {
  id: number;
  ticker: string;
  ticker_name: string;
  trade_type: string;
  price: number;
  quantity: number;
  executed_at: string;
  realized_pnl?: number;
  return_rate?: number;
}

interface TradeLogsProps {
  logs: TradeLog[];
  isModalMode?: boolean;
}

export function TradeLogs({ logs, isModalMode = false }: TradeLogsProps) {
  const { selectedTimezone } = useTimezone();
  return (
    <div className={isModalMode 
      ? "bg-transparent w-full h-[75vh] flex flex-col" 
      : "bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl overflow-hidden shadow-xl flex flex-col h-[75vh]"
    }>
      <div className={`shrink-0 p-6 border-b border-zinc-800 flex justify-between items-center ${isModalMode ? 'bg-transparent px-0 pt-0' : 'bg-zinc-950/20'}`}>
        <h3 className="text-lg font-semibold text-white tracking-tight flex items-center gap-2">
          <span className="w-1.5 h-4 bg-emerald-500 rounded-full animate-pulse"></span>
          실시간 체결 로그 (Execution Logs)
        </h3>
      </div>
      <div className="overflow-auto flex-1 min-h-0">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 z-20 bg-zinc-900">
            <tr className="text-zinc-400 text-xs tracking-wider uppercase">
              <th className="p-4 font-semibold">Time</th>
              <th className="p-4 font-semibold">Ticker</th>
              <th className="p-4 font-semibold">Type</th>
              <th className="p-4 font-semibold">Price</th>
              <th className="p-4 font-semibold">Qty</th>
              <th className="p-4 font-semibold">Total</th>
              <th className="p-4 font-semibold text-right">Return Rate</th>
              <th className="p-4 font-semibold text-right">Realized PnL</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/40">
            {logs.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-8 text-center text-zinc-500 text-sm">No trading logs yet.</td>
              </tr>
            ) : (
              logs.map((log) => {
                const isSell = log.trade_type === 'SELL';
                const hasPnL = log.realized_pnl !== undefined && log.realized_pnl !== null;
                const pnl = hasPnL ? log.realized_pnl! : 0;
                const rate = hasPnL ? log.return_rate! : 0;
                
                const isProfit = pnl >= 0;
                
                return (
                  <tr key={log.id} className="hover:bg-zinc-800/20 transition-colors">
                    <td className="p-4 text-xs text-zinc-400 font-mono whitespace-nowrap">
                      <span className="text-[9px] bg-zinc-800/80 text-zinc-500 px-1.5 py-0.5 rounded font-black tracking-widest mr-1.5 select-none">{selectedTimezone.abbr}</span>
                      {new Date(log.executed_at).toLocaleString('ko-KR', {
                        timeZone: selectedTimezone.timeZone,
                      })}
                    </td>
                    <td className="p-4">
                      <div className="font-semibold text-white text-sm">{log.ticker_name || log.ticker}</div>
                      <div className="text-[10px] text-zinc-500 font-mono">{log.ticker}</div>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold border tracking-wider ${
                        log.trade_type === 'BUY' 
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                          : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                      }`}>
                        {log.trade_type}
                      </span>
                    </td>
                    <td className="p-4 text-zinc-300 font-mono text-sm">${log.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className="p-4 text-zinc-300 font-mono text-sm">{log.quantity.toLocaleString()}주</td>
                    <td className="p-4 font-medium text-zinc-300 font-mono text-sm">
                      ${(log.price * log.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="p-4 text-right">
                      {isSell && hasPnL ? (
                        <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${
                          isProfit 
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        }`}>
                          {isProfit ? '▲' : '▼'} {Math.abs(rate).toFixed(2)}%
                        </span>
                      ) : (
                        <span className="text-zinc-600 font-mono text-sm">—</span>
                      )}
                    </td>
                    <td className="p-4 text-right">
                      {isSell && hasPnL ? (
                        <span className={`text-sm font-bold font-mono tracking-tight ${
                          isProfit ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          {isProfit ? '+' : '-'}${Math.abs(pnl).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </span>
                      ) : (
                        <span className="text-zinc-600 font-mono text-sm">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

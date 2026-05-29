"use client";

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
}

export function TradeLogs({ logs }: TradeLogsProps) {
  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl overflow-hidden shadow-xl mt-6">
      <div className="p-6 border-b border-zinc-800 flex justify-between items-center bg-zinc-950/20">
        <h3 className="text-lg font-semibold text-white tracking-tight flex items-center gap-2">
          <span className="w-1.5 h-4 bg-emerald-500 rounded-full"></span>
          실시간 체결 로그 (Execution Logs)
        </h3>
        <span className="text-[10px] text-zinc-500 font-medium">실시간 동기화 중</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-zinc-950/40 text-zinc-400 text-xs tracking-wider uppercase border-b border-zinc-800/50">
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
                    <td className="p-4 text-xs text-zinc-400 font-mono">
                      {new Date(log.executed_at).toLocaleString()}
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
                        <span className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs font-bold ${
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

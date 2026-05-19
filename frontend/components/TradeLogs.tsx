"use client";

export interface TradeLog {
  id: number;
  ticker: string;
  ticker_name: string;
  trade_type: string;
  price: number;
  quantity: number;
  executed_at: string;
}

interface TradeLogsProps {
  logs: TradeLog[];
}

export function TradeLogs({ logs }: TradeLogsProps) {
  return (
    <div className="bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl overflow-hidden shadow-xl mt-6">
      <div className="p-6 border-b border-zinc-800">
        <h3 className="text-lg font-semibold text-white">Execution Logs</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-zinc-950/50 text-zinc-400 text-sm">
              <th className="p-4 font-medium">Time</th>
              <th className="p-4 font-medium">Ticker</th>
              <th className="p-4 font-medium">Type</th>
              <th className="p-4 font-medium">Price</th>
              <th className="p-4 font-medium">Qty</th>
              <th className="p-4 font-medium text-right">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {logs.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-8 text-center text-zinc-500">No trading logs yet.</td>
              </tr>
            ) : (
              logs.map((log) => (
                <tr key={log.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="p-4 text-zinc-300">
                    {new Date(log.executed_at).toLocaleString()}
                  </td>
                  <td className="p-4">
                    <div className="font-medium text-white">{log.ticker_name}</div>
                    <div className="text-xs text-zinc-500">{log.ticker}</div>
                  </td>
                  <td className="p-4">
                    <span className={`inline-flex px-2 py-1 rounded-md text-xs font-medium ${
                      log.trade_type === 'BUY' 
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                        : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    }`}>
                      {log.trade_type}
                    </span>
                  </td>
                  <td className="p-4 text-zinc-300 font-mono">${log.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td className="p-4 text-zinc-300 font-mono">{log.quantity.toLocaleString()}주</td>
                  <td className="p-4 text-right font-medium text-white font-mono">
                    ${(log.price * log.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

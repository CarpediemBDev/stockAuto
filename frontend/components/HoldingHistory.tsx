"use client";

import React from "react";
import useSWR from "swr";
import { History, TrendingDown, TrendingUp } from "lucide-react";
import { useTranslations } from "next-intl";

import { fetcher } from "@/lib/api";
import { pollInterval } from "@/lib/sse";
import { getProfitColor } from "@/lib/theme";
import { cn, formatKrw, usdToKrw } from "@/lib/utils";
import { useTimezone } from "@/store/timezoneStore";
import type { TradeLog } from "./TradeLogs";

/**
 * 한 번에 끌어오는 체결 건수 상한. 서버는 필터를 DB에서 걸고 limit을 그 뒤에 적용하므로
 * 이 값은 "이 종목의 최근 N건"을 뜻한다. 상한에 닿으면 그보다 오래된 체결은 응답에 없고,
 * 따라서 보유 시작일 계산도 관측 창 안에서만 유효하다 - 그 사실을 화면이 밝힌다.
 */
const HISTORY_LIMIT = 500;

export interface HoldingHistoryTarget {
  /** 거래소 접두를 제거한 티커. 서버도 접두를 받아주지만 표시·키 모두 이 형태를 쓴다. */
  ticker: string;
  ticker_name: string;
  avg_price: number;
  quantity: number;
  fx_rate?: number;
}

interface SliceHistory {
  strategyType: string;
  /** 최신순 정렬된 이 슬라이스의 체결들. */
  logs: TradeLog[];
  /**
   * 현재 열려 있는 포지션이 시작된 시각. 전량 매도로 수량이 0이 되면 초기화되므로,
   * 같은 종목을 팔았다 다시 산 경우 "마지막으로 다시 산 시점"을 가리킨다.
   * 관측 창 안에서 포지션이 열린 흔적이 없으면 null이다.
   */
  openedAt: string | null;
  buyCount: number;
  sellCount: number;
}

/**
 * 슬라이스(전략)별로 나눠 현재 포지션의 시작 시각을 계산한다.
 *
 * 티커 하나를 여러 전략 슬롯으로 동시에 보유할 수 있어(holdings의 유니크 제약이
 * strategy_type까지 포함) 전체를 한 줄로 이어 세면 수량이 뒤섞인다. 슬롯마다 따로 걷는다.
 */
function buildSlices(logs: TradeLog[]): SliceHistory[] {
  const groups = new Map<string, TradeLog[]>();
  for (const log of logs) {
    const key = log.strategy_type || "";
    const bucket = groups.get(key);
    if (bucket) bucket.push(log);
    else groups.set(key, [log]);
  }

  const slices: SliceHistory[] = [];
  for (const [strategyType, bucket] of groups) {
    // 서버는 최신순으로 주므로 뒤집어서 시간순으로 걷는다.
    const ascending = [...bucket].reverse();
    let quantity = 0;
    let openedAt: string | null = null;
    let buyCount = 0;
    let sellCount = 0;

    for (const log of ascending) {
      if (log.trade_type === "BUY") {
        // 수량이 0인 상태에서의 매수가 포지션의 시작이다. 추가매수(피라미딩)는 시작을 옮기지 않는다.
        if (quantity <= 0) openedAt = log.executed_at;
        quantity += log.quantity;
        buyCount += 1;
      } else {
        quantity -= log.quantity;
        sellCount += 1;
        if (quantity <= 0) {
          quantity = 0;
          openedAt = null;
        }
      }
    }

    slices.push({ strategyType, logs: bucket, openedAt, buyCount, sellCount });
  }

  // 열린 포지션을 가진 슬라이스를 위로, 그 안에서는 최근에 시작한 순서로.
  return slices.sort((a, b) => {
    if (!!a.openedAt !== !!b.openedAt) return a.openedAt ? -1 : 1;
    return (b.openedAt || "").localeCompare(a.openedAt || "");
  });
}

/**
 * 보유 종목 하나의 체결 이력. "언제 얼마에 샀는지"가 이 화면의 유일한 존재 이유다.
 *
 * 원장은 trade_logs 하나뿐이다(holdings에는 매수 시각이 없고, updated_at은 트레일링 고점
 * 갱신마다 덮여써서 매수일 대용이 될 수 없다). 그래서 여기서 보여주는 모든 시각·단가는
 * 서버가 체결 시점에 남긴 값이지 화면에서 추정한 값이 아니다.
 */
export function HoldingHistory({
  target,
  displayCurrency = "KRW",
}: {
  target: HoldingHistoryTarget | null;
  displayCurrency?: "KRW" | "USD";
}) {
  const t = useTranslations("components");
  const { selectedTimezone } = useTimezone();

  const { data, isLoading, error } = useSWR(
    target ? `/trades?ticker=${encodeURIComponent(target.ticker)}&limit=${HISTORY_LIMIT}` : null,
    fetcher,
    { refreshInterval: pollInterval(30000) },
  );

  const logs: TradeLog[] = React.useMemo(() => (Array.isArray(data) ? data : []), [data]);
  const slices = React.useMemo(() => buildSlices(logs), [logs]);
  const truncated = logs.length >= HISTORY_LIMIT;

  const money = (usd: number) =>
    displayCurrency === "USD"
      ? `$${usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : formatKrw(usdToKrw(usd, target?.fx_rate));

  const formatTime = (iso: string) => {
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return iso;
    return parsed.toLocaleString("ko-KR", { timeZone: selectedTimezone.timeZone });
  };

  if (!target) return null;

  return (
    <div className="flex flex-col gap-4">
      {/* 요약 - 카드에 있는 값과 같은 출처(브로커 잔고)다. 이력과 나란히 두어야 평단가가
          어떤 체결들의 결과인지 대조할 수 있다. */}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 bg-zinc-900/60 border border-zinc-800/80 rounded-xl px-4 py-3">
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
            {t("portfolio.avg_price")}
          </div>
          <div className="text-sm font-bold text-slate-200 font-mono">{money(target.avg_price)}</div>
        </div>
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
            {t("portfolio.quantity")}
          </div>
          <div className="text-sm font-bold text-slate-200 font-mono">
            {target.quantity.toLocaleString()}
            {t("common.shares_suffix")}
          </div>
        </div>
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
            {t("portfolio.history_fill_count")}
          </div>
          <div className="text-sm font-bold text-slate-200 font-mono">{logs.length.toLocaleString()}</div>
        </div>
      </div>

      {isLoading && (
        <div className="text-zinc-500 text-sm p-8 text-center animate-pulse">
          {t("portfolio.history_loading")}
        </div>
      )}

      {!isLoading && error && (
        <div className="text-rose-400 text-sm p-8 text-center">{t("portfolio.history_failed")}</div>
      )}

      {!isLoading && !error && logs.length === 0 && (
        <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-8 text-center">
          <History className="text-zinc-600 mx-auto mb-3" size={28} />
          <p className="text-sm font-bold text-slate-300">{t("portfolio.history_empty_title")}</p>
          {/* 봇이 사지 않은 보유분(EXTERNAL)은 원장에 체결이 없는 것이 정상이다.
              "기록이 사라졌다"로 읽히지 않도록 이유를 함께 적는다. */}
          <p className="text-zinc-500 text-xs mt-2 leading-relaxed">{t("portfolio.history_empty_hint")}</p>
        </div>
      )}

      {truncated && (
        <p className="text-[11px] text-amber-400/90 leading-relaxed">
          {t("portfolio.history_truncated", { limit: HISTORY_LIMIT })}
        </p>
      )}

      {slices.map((slice) => (
        <div
          key={slice.strategyType || "unknown"}
          className="border border-zinc-800/80 rounded-xl overflow-hidden"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 bg-zinc-900/60 px-4 py-2.5 border-b border-zinc-800/80">
            <div className="flex items-center gap-2">
              <span className="text-[9px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase bg-indigo-500/15 text-indigo-400 border-indigo-500/30">
                {slice.strategyType ? slice.strategyType.replaceAll("_", " ") : t("portfolio.history_no_strategy")}
              </span>
              <span className="text-[10px] text-zinc-500 font-semibold">
                {t("portfolio.history_counts", { buys: slice.buyCount, sells: slice.sellCount })}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                {t("portfolio.history_opened_at")}
              </span>
              <span className="text-xs font-bold text-emerald-400 font-mono">
                {slice.openedAt ? formatTime(slice.openedAt) : t("portfolio.history_opened_unknown")}
              </span>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[640px]">
              <thead>
                <tr className="text-zinc-500 text-[10px] tracking-wider uppercase bg-zinc-950/40">
                  <th className="px-4 py-2 font-semibold">{t("portfolio.history_col_time")}</th>
                  <th className="px-3 py-2 font-semibold">{t("portfolio.history_col_type")}</th>
                  <th className="px-3 py-2 font-semibold text-right">{t("portfolio.history_col_price")}</th>
                  <th className="px-3 py-2 font-semibold text-right">{t("portfolio.history_col_qty")}</th>
                  <th className="px-3 py-2 font-semibold text-right">{t("portfolio.history_col_total")}</th>
                  <th className="px-4 py-2 font-semibold text-right">{t("portfolio.history_col_pnl")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/40">
                {slice.logs.map((log) => {
                  const isSell = log.trade_type === "SELL";
                  const hasPnL = isSell && log.realized_pnl !== undefined && log.realized_pnl !== null;
                  const pnl = hasPnL ? log.realized_pnl! : 0;
                  const rate = hasPnL ? log.return_rate ?? 0 : 0;

                  return (
                    <tr key={log.id} className="hover:bg-zinc-800/20 transition-colors">
                      <td className="px-4 py-2.5 text-[11px] text-zinc-400 font-mono whitespace-nowrap">
                        <span className="text-[9px] bg-zinc-800/80 text-zinc-500 px-1.5 py-0.5 rounded font-black tracking-widest mr-1.5 select-none">
                          {selectedTimezone.abbr}
                        </span>
                        {formatTime(log.executed_at)}
                      </td>
                      <td className="px-3 py-2.5">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold border tracking-wider",
                            isSell
                              ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                              : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
                          )}
                        >
                          {isSell ? <TrendingDown size={10} /> : <TrendingUp size={10} />}
                          {log.trade_type}
                        </span>
                        {/* 매수 당시의 판단 근거. 서버가 체결과 함께 남긴 값이라 사후 재계산이 아니다. */}
                        {!isSell && !!log.signal_score && (
                          <span className="ml-1.5 text-[9px] text-zinc-500 font-mono">
                            {t("portfolio.history_signal_score", { score: log.signal_score })}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-300 font-mono text-xs">
                        {money(log.price)}
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-300 font-mono text-xs">
                        {log.quantity.toLocaleString()}
                        {t("common.shares_suffix")}
                      </td>
                      <td className="px-3 py-2.5 text-right text-slate-300 font-mono text-xs">
                        {money(log.price * log.quantity)}
                      </td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        {hasPnL ? (
                          <span className={cn("text-xs font-bold font-mono", getProfitColor(pnl))}>
                            {pnl >= 0 ? "+" : "-"}
                            {money(Math.abs(pnl))}
                            <span className="text-[10px] ml-1 opacity-80">
                              ({rate >= 0 ? "+" : ""}
                              {rate.toFixed(2)}%)
                            </span>
                          </span>
                        ) : (
                          <span className="text-zinc-600 font-mono text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

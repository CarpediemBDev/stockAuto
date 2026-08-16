"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { pollInterval } from "@/lib/sse";

export interface MarketQuote {
  symbol: string;
  current: number;
  change: number;
  change_pct: number;
}

export interface MarketOverview {
  market_condition?: string;
  sentiment?: string;
  nasdaq: MarketQuote | null;
  exchange_rate: MarketQuote | null;
}

export type MarketRegime = "BULLISH" | "BEARISH" | "NEUTRAL";

const REGIMES: readonly MarketRegime[] = ["BULLISH", "BEARISH", "NEUTRAL"];

// 시장 국면 SSOT: GET /market/overview 의 market_condition(없으면 sentiment).
// 예전에 AIMarketRegimeWidget이 존재하지도 않는 adminSettings.market_regime을 읽고
// "BULLISH"로 폴백해, 헤더·관제탑과 다른 국면을 표시하던 결함이 있었다. 국면을 읽는
// 곳은 반드시 이 훅을 거친다.
export function useMarketOverview() {
  const { data, error, isLoading } = useSWR<MarketOverview>("/market/overview", fetcher, {
    refreshInterval: pollInterval(15000),
  });

  const raw = data?.market_condition ?? data?.sentiment;
  // 아는 값이 아니면 추측하지 않고 undefined로 둔다. 소비자는 국면 미확정 상태를
  // 별도로 표현해야 하며, 임의의 기본 국면을 지어내면 안 된다.
  const regime = REGIMES.find((r) => r === raw);

  return { data, regime, error, isLoading };
}

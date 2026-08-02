"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";

// 전략 카탈로그 항목 타입. 예전엔 StrategyCatalog/CurrentStrategyBadge 두 곳에
// 각각 중복 선언돼 있었다. 여기 한 곳을 SSOT로 삼는다.
export interface Strategy {
  id: string;
  name: string;
  name_en?: string;
  description?: string;
  tier: "gold" | "silver" | "bronze" | "sandbox" | "single";
  regime: "ALL" | "BULLISH" | "BEARISH" | "NEUTRAL";
  summary_ko?: string;
  sort_order?: number;
}

// 기본 전략 규칙도 한 곳에서만 관리한다.
export const DEFAULT_STRATEGY_ID = "regime_switching";

// 선택 가능한 전략 카탈로그 (SSOT: GET /strategies/catalog).
// SWR 키가 동일하므로 여러 컴포넌트가 호출해도 요청은 한 번만 나가고 캐시를 공유한다.
export function useStrategyCatalog() {
  const { data: strategies, error, isLoading } = useSWR<Strategy[]>(
    "/strategies/catalog",
    fetcher,
  );
  return { strategies, error, isLoading };
}

// 현재 실행 중인 전략 = /admin 의 strategy_type 을 카탈로그와 조인해 해석한다.
// 기본값(regime_switching)·find 조인 로직을 여기 한 곳에 모은다.
export function useCurrentStrategy() {
  const { data: adminSettings } = useSWR("/admin", fetcher);
  const { strategies } = useStrategyCatalog();

  const currentId: string = adminSettings?.strategy_type || DEFAULT_STRATEGY_ID;
  const current = strategies?.find((s) => s.id === currentId);

  return { currentId, current, isLoading: !adminSettings || !strategies };
}

"use client";

/**
 * 데이터 신선도("몇 초 전 기준") 계산 훅 (Phase 4).
 *
 * 기존 컴포넌트별 setInterval + nowTs state 중복을 대체한다:
 *  - 단일 공유 클럭: 모든 배지가 하나의 1초 틱을 useSyncExternalStore로 구독(타이머 N→1).
 *  - clock-skew 보정: SSE connected 이벤트의 서버 시각으로 산출한 오프셋을 반영해
 *    now(클라)-captured_at(서버) 계산의 시계 차이를 흡수.
 *  - 3-상태: fresh / stale / disconnected. disconnected는 SSE 연결이 끊겼을 때
 *    "낡음의 원인이 전송 단절"임을 정직하게 구분(폴링으론 불가능했던 신호).
 *
 * 신선도는 데이터 속성이므로 항상 서버 captured_at 기준으로 계산한다(도착 시각 아님).
 */
import { useSyncExternalStore } from "react";
import { useTranslations } from "next-intl";

// ── 단일 공유 클럭 ──────────────────────────────────────────────
const listeners = new Set<() => void>();
let sharedNow = Date.now();
let timer: ReturnType<typeof setInterval> | null = null;

function ensureTimer() {
  if (timer) return;
  timer = setInterval(() => {
    sharedNow = Date.now();
    listeners.forEach((l) => l());
  }, 1000);
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  ensureTimer();
  return () => {
    listeners.delete(cb);
    if (listeners.size === 0 && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

// 초기 렌더(SSR·하이드레이션)는 0을 반환 → 배지 미표시로 서버/클라 일치.
// 마운트 후 구독이 시작되면 실제 시각으로 갱신되며 배지가 나타난다.
const getSnapshot = () => sharedNow;
const getServerSnapshot = () => 0;

/** 1초 간격으로 갱신되는 공유 현재 시각(ms). 아직 마운트 전이면 0. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export type FreshnessStatus = "fresh" | "stale" | "disconnected";

export interface FreshnessResult {
  ageSec: number | null;
  isStale: boolean;
  label: string;
  status: FreshnessStatus;
}

export interface FreshnessOptions {
  /** 낡음 판정 임계(초). 기본 90. */
  staleAfterSec?: number;
  /** 서버-클라 시계 오프셋(ms): now(클라)+offset ≈ 서버 now. SSE connected에서 산출. */
  serverOffsetMs?: number;
  /** 전송이 끊긴 상태인지(SSE disconnected). true면 status=disconnected. */
  disconnected?: boolean;
}

/**
 * captured_at(서버 측정 시각)로부터 나이·낡음·상태를 계산한다.
 * 마운트 전(now=0)이나 capturedAt이 없으면 배지를 숨긴다(ageSec=null, label="").
 */
export function useFreshness(
  capturedAt: string | null | undefined,
  options: FreshnessOptions = {},
): FreshnessResult {
  const now = useNow();
  const t = useTranslations("freshness");
  const staleAfterSec = options.staleAfterSec ?? 90;
  const offset = options.serverOffsetMs ?? 0;

  const ageLabel = (ageSec: number): string =>
    ageSec >= 60 ? t("min", { n: Math.floor(ageSec / 60) }) : t("sec", { n: ageSec });

  const empty = (status: FreshnessStatus): FreshnessResult => ({
    ageSec: null,
    isStale: false,
    label: "",
    status,
  });

  if (options.disconnected) return empty("disconnected");
  if (!capturedAt || now === 0) return empty("fresh");

  const captured = new Date(capturedAt).getTime();
  if (Number.isNaN(captured)) return empty("fresh");

  const ageSec = Math.floor((now + offset - captured) / 1000);
  const isStale = ageSec >= staleAfterSec;
  return {
    ageSec,
    isStale,
    label: ageLabel(Math.max(0, ageSec)),
    status: isStale ? "stale" : "fresh",
  };
}

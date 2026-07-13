"use client";

/**
 * SSE 이벤트 스트림 프로바이더 (Phase 1~4).
 *
 * 단일 /events 스트림을 열고, 수신 이벤트를 SWR 캐시에 주입(mutate)한다.
 * → 컴포넌트는 기존 useSWR(key)를 그대로 쓰되, refreshInterval을 pollInterval()로 감싸
 *   SSE on일 때만 폴링이 멈추고 push로 갱신된다(전송 계층 교체, 컴포넌트 로직 무변경).
 *
 * 회귀 0 원칙: NEXT_PUBLIC_SSE_ENABLED === "true" 일 때만 연결을 연다.
 * 기본(off)에서는 아무 것도 하지 않아 기존 폴링 동작·E2E에 영향이 없다.
 *
 * 또한 연결 상태와 서버 시계 오프셋을 컨텍스트로 노출한다(Phase 4 useFreshness가 소비).
 */
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { EventStreamClient, SSE_ENABLED, type SseState } from "@/lib/sse";
import { useAuthStore } from "@/store/authStore";

// event 이름 → SWR 캐시 키 (백엔드 app/core/sse.py 이벤트 상수와의 계약).
// 서버는 변경 시 data=null(invalidate)로 발행 → 여기서 해당 키를 revalidate(재조회)한다.
const EVENT_TO_KEY: Record<string, string> = {
  // 공용 채널
  scanner_latest: "/scanner/latest",
  swing: "/scanner/swing-predict",
  after_hours: "/scanner/after-hours-candidates",
  market: "/market/overview",
  // 유저 채널
  balance: "/account/balance",
  holdings: "/account/holdings",
  trades: "/trades",
  bot_status: "/bot/status",
  watchlist: "/watchlist",
  // 관리자 채널
  admin_users: "/admin/users",
};

// 파이프라인 제어 이벤트(connected/heartbeat)는 캐시 주입 대상이 아니다.
const CONTROL_EVENTS = new Set(["connected", "heartbeat"]);

export interface SseConnection {
  /** disabled: 플래그 off / connecting·open·closed: 실제 연결 상태 */
  status: "disabled" | SseState;
  /** now(클라)+offset ≈ 서버 now. connected 이벤트에서 산출. */
  serverOffsetMs: number;
  /** 낡음 판정 시 "전송 단절"로 볼지 — SSE on인데 open이 아닐 때 true. */
  disconnected: boolean;
}

const SseConnectionContext = createContext<SseConnection>({
  status: "disabled",
  serverOffsetMs: 0,
  disconnected: false,
});

/** 컴포넌트에서 SSE 연결 상태·시계 오프셋을 읽는다(3-상태 낡음 배지용). */
export function useSseConnection(): SseConnection {
  return useContext(SseConnectionContext);
}

export function EventStreamProvider({ children }: { children: React.ReactNode }) {
  const { mutate } = useSWRConfig();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [status, setStatus] = useState<"disabled" | SseState>(
    SSE_ENABLED ? "closed" : "disabled",
  );
  const [serverOffsetMs, setServerOffsetMs] = useState(0);
  const offsetRef = useRef(0);

  useEffect(() => {
    if (!SSE_ENABLED || !isAuthenticated) return;

    const client = new EventStreamClient(
      (event, data) => {
        if (event === "connected") {
          // 서버 시각으로 clock-skew 오프셋 1회 산출: offset = serverNow - clientNow.
          const serverTime = (data as { server_time?: string })?.server_time;
          if (serverTime) {
            const parsed = new Date(serverTime).getTime();
            if (!Number.isNaN(parsed)) {
              const offset = parsed - Date.now();
              offsetRef.current = offset;
              setServerOffsetMs(offset);
            }
          }
          return;
        }
        if (CONTROL_EVENTS.has(event)) return;

        const key = EVENT_TO_KEY[event];
        if (!key) return;
        if (data === null || data === undefined) {
          // invalidate: 서버가 "바뀌었다"만 알림 → 최신값을 1회 재조회(변경 시에만).
          void mutate(key);
        } else {
          // full-payload: 서버가 값을 직접 밀어줌 → 재요청 없이 캐시에 주입.
          void mutate(key, data, false);
        }
      },
      (nextState) => setStatus(nextState),
    );

    client.start();
    return () => client.stop();
  }, [isAuthenticated, mutate]);

  const value = useMemo<SseConnection>(
    () => ({
      status,
      serverOffsetMs,
      // SSE를 쓰기로 했는데 open이 아니면 전송 단절로 간주(3-상태 disconnected).
      disconnected: SSE_ENABLED && status !== "open" && status !== "disabled",
    }),
    [status, serverOffsetMs],
  );

  return (
    <SseConnectionContext.Provider value={value}>
      {children}
    </SseConnectionContext.Provider>
  );
}

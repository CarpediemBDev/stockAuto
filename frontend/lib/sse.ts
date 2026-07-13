/**
 * fetch 기반 SSE 클라이언트 (Phase 1).
 *
 * 네이티브 EventSource는 Authorization 헤더를 못 실으므로(우리 인증은 Bearer),
 * fetch + ReadableStream으로 직접 프레임을 파싱한다. 토큰은 헤더로만 전달하고
 * URL 쿼리에는 절대 싣지 않는다(프라이버시).
 *
 * 특징:
 *  - 지터 백오프 자동 재연결
 *  - 401 시 1회 세션 갱신 후 즉시 재연결
 *  - 연결 상태 콜백(connecting/open/closed) — 3-상태 낡음 배지(Phase 4)의 기반
 */
import { refreshAuthSession } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

export type SseEventHandler = (event: string, data: unknown) => void;
export type SseState = "connecting" | "open" | "closed";
export type SseStateHandler = (state: SseState) => void;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
const MAX_BACKOFF_MS = 30_000;
const INITIAL_BACKOFF_MS = 1_000;

/** SSE 전역 스위치. 기본 on(opt-out) — NEXT_PUBLIC_SSE_ENABLED="false"로만 끈다(폴링 복귀). */
export const SSE_ENABLED = process.env.NEXT_PUBLIC_SSE_ENABLED !== "false";

/**
 * SWR refreshInterval 헬퍼.
 * SSE on → 0(폴링 중단, push가 갱신 담당) / off → 기존 주기 그대로.
 * SSE on에서도 SWR 기본 revalidateOnFocus가 안전망으로 남는다.
 */
export const pollInterval = (ms: number): number => (SSE_ENABLED ? 0 : ms);

export class EventStreamClient {
  private controller: AbortController | null = null;
  private closed = false;
  private backoffMs = INITIAL_BACKOFF_MS;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly onEvent: SseEventHandler,
    private readonly onState?: SseStateHandler,
  ) {}

  start(): void {
    this.closed = false;
    void this.connect();
  }

  stop(): void {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.controller?.abort();
    this.onState?.("closed");
  }

  private async connect(): Promise<void> {
    if (this.closed) return;
    this.onState?.("connecting");
    this.controller = new AbortController();
    const token = useAuthStore.getState().accessToken;

    try {
      const res = await fetch(`${API_BASE}/events`, {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        signal: this.controller.signal,
        cache: "no-store",
      });

      if (res.status === 401) {
        // 만료된 access 토큰: 1회 갱신 후 즉시 재시도(백오프 없이)
        try {
          await refreshAuthSession();
          this.scheduleReconnect(0);
        } catch {
          this.scheduleReconnect();
        }
        return;
      }
      if (!res.ok || !res.body) {
        this.scheduleReconnect();
        return;
      }

      this.onState?.("open");
      this.backoffMs = INITIAL_BACKOFF_MS;
      await this.readStream(res.body);
    } catch {
      // abort(정상 종료) 포함 — closed면 조용히 종료
      if (!this.closed) this.scheduleReconnect();
      return;
    }

    if (!this.closed) this.scheduleReconnect();
  }

  private async readStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (!this.closed) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        this.dispatchFrame(frame);
      }
    }
  }

  private dispatchFrame(frame: string): void {
    // 주석 프레임(keep-alive ": ping") 무시
    if (!frame || frame.startsWith(":")) return;

    let event = "message";
    let dataStr = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
    }
    if (!dataStr) return;
    try {
      this.onEvent(event, JSON.parse(dataStr));
    } catch {
      /* 파싱 불가 프레임은 조용히 폐기 */
    }
  }

  private scheduleReconnect(delayMs: number = this.backoffMs): void {
    if (this.closed) return;
    this.onState?.("connecting");
    const jitter = Math.random() * 250;
    this.reconnectTimer = setTimeout(() => void this.connect(), delayMs + jitter);
    this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
  }
}

import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 에러 객체에서 안전하게 메시지를 추출합니다.
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') return error;
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
    if (message != null) return String(message);
  }
  return "알 수 없는 오류가 발생했습니다.";
}

/**
 * 사용자에게 토스트/상태 UI로 이미 처리한 오류를 Next.js 개발 오버레이에 올리지 않도록 기록합니다.
 */
export function reportHandledError(context: string, error: unknown): string {
  const message = getErrorMessage(error);
  if (process.env.NODE_ENV !== "production") {
    console.debug(`[Handled] ${context}:`, message);
  }
  return message;
}

/**
 * 시그널 스코어에 따른 텍스트/보더 색상 테마 반환 (80점 이상: rose/indigo, 60점 이상: amber, 기타: blue/zinc 계열)
 */
export function getScoreColor(score: number): string {
  if (score >= 80) return "text-rose-500 bg-rose-500/10 border-rose-500/20";
  if (score >= 60) return "text-amber-500 bg-amber-500/10 border-amber-500/20";
  return "text-blue-400 bg-blue-500/10 border-blue-500/20";
}

/**
 * 시그널 스코어에 따른 게이지 바 색상 반환
 */
export function getScoreBarColor(score: number): string {
  if (score >= 80) return "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]";
  if (score >= 60) return "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]";
  return "bg-blue-400";
}

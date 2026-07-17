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
 * 환율 폴백 기본값(1 USD = 1350원). 서버가 fx_rate를 주지 못할 때만 사용하는 SSOT 상수.
 * 이 값을 여기 한 곳에서만 관리하고, 컴포넌트에 매직넘버로 흩뿌리지 않는다.
 */
export const DEFAULT_FX_RATE = 1350;

/**
 * 유효한 환율(양수)이면 그대로, 아니면 기본 폴백(DEFAULT_FX_RATE)을 반환한다.
 */
export function resolveFxRate(fxRate?: number | null): number {
  return fxRate && fxRate > 0 ? fxRate : DEFAULT_FX_RATE;
}

/**
 * USD 금액을 원화로 환산한다(미국 주식 가격 등 → 원화 표시).
 */
export function usdToKrw(usdAmount: number, fxRate?: number | null): number {
  return usdAmount * resolveFxRate(fxRate);
}

/**
 * 원화 금액을 USD로 환산한다(원화로 저장된 총자산 등 → USD 표시).
 */
export function krwToUsd(krwAmount: number, fxRate?: number | null): number {
  return krwAmount / resolveFxRate(fxRate);
}

/**
 * 원화 금액을 "1,234,567원" 형식 문자열로 포맷한다(소수점 절사).
 */
export function formatKrw(krwAmount: number): string {
  return `${krwAmount.toLocaleString(undefined, { maximumFractionDigits: 0 })}원`;
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

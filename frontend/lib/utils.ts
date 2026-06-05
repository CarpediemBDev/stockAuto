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

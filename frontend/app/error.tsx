"use client"; // 에러 바운더리는 반드시 클라이언트 컴포넌트여야 한다(Next.js 규약)

import React, { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCcw, Home } from "lucide-react";

/**
 * 전역 에러 바운더리 (App Router).
 *
 * 런타임 오류가 페이지·중첩 레이아웃에서 던져질 때 백지 화면 대신 이 폴백을 보여준다.
 * unstable_retry는 Next 16.2.0에 도입된 프롭으로, 세그먼트 데이터를 재조회하며 다시 렌더한다
 * (구버전 reset은 재조회 없이 상태만 초기화 — 데이터 오류 복구엔 부적합해 쓰지 않는다).
 *
 * 주의: 이 파일은 루트 layout.tsx 자체의 오류는 잡지 못한다(Next 규약).
 *       루트 레이아웃까지 감싸려면 app/global-error.tsx가 별도로 필요하다.
 */
export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    // 콘솔에 남겨 개발·운영 로그 수집 경로를 확보한다(외부 리포팅 도구 미도입).
    console.error("[GlobalError]", error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-zinc-900/80 backdrop-blur-md border border-zinc-800 rounded-2xl p-6 shadow-xl flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-rose-500/20 rounded-lg text-rose-500">
            <AlertTriangle size={20} />
          </div>
          <div>
            <h2 className="font-bold text-base">화면을 표시하는 중 문제가 발생했습니다</h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              일시적인 오류일 수 있습니다. 다시 시도하거나 대시보드로 이동해 주세요.
            </p>
          </div>
        </div>

        {/* digest는 서버 로그와 대조할 수 있는 식별자라 노출한다(에러 원문은 감춘다) */}
        {error.digest && (
          <p className="text-[11px] font-mono text-zinc-500 break-all">
            오류 코드: {error.digest}
          </p>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => unstable_retry()}
            className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 transition-colors rounded-xl py-2.5 text-sm font-bold"
          >
            <RotateCcw size={15} />
            다시 시도
          </button>
          <Link
            href="/"
            className="flex-1 flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 transition-colors rounded-xl py-2.5 text-sm font-bold"
          >
            <Home size={15} />
            대시보드
          </Link>
        </div>
      </div>
    </div>
  );
}

"use client"; // 에러 바운더리는 반드시 클라이언트 컴포넌트여야 한다(Next.js 규약)

import React, { useEffect } from "react";

/**
 * 최상위 전역 에러 바운더리 (App Router).
 *
 * app/error.tsx가 잡지 못하는 **루트 layout.tsx·template 자체의 오류**를 담당한다.
 * 활성화되면 루트 레이아웃을 통째로 대체하므로(Next 규약):
 *   - 자체 <html>/<body> 태그를 반드시 포함해야 한다.
 *   - 루트 레이아웃이 주입하던 폰트·globals.css·Provider가 모두 사라지므로,
 *     외부 의존 없이 인라인 스타일만으로 자립해야 한다(그래서 Tailwind 클래스 대신 style 사용).
 *   - metadata/generateMetadata export는 지원되지 않아 React <title>로 대체한다.
 *
 * unstable_retry는 Next 16.2.0 도입 프롭으로 세그먼트를 재조회하며 다시 렌더한다
 * (구버전 reset은 재조회 없이 상태만 초기화 — 데이터 오류 복구엔 부적합).
 */
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error("[GlobalError:root]", error);
  }, [error]);

  return (
    // global-error는 <html>/<body>를 직접 포함해야 한다(루트 레이아웃 대체)
    <html lang="ko">
      <title>오류 - StockAuto</title>
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1rem",
          background:
            "radial-gradient(circle at 50% 0%, #1e1b4b 0%, #09090b 70%)",
          color: "#ededed",
          fontFamily:
            '-apple-system, BlinkMacSystemFont, system-ui, Roboto, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "26rem",
            background: "rgba(24, 24, 27, 0.8)",
            border: "1px solid #27272a",
            borderRadius: "1rem",
            padding: "1.5rem",
            boxShadow: "0 20px 40px rgba(0,0,0,0.4)",
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          <div>
            <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700 }}>
              앱을 불러오는 중 심각한 오류가 발생했습니다
            </h2>
            <p
              style={{
                margin: "0.375rem 0 0",
                fontSize: "0.75rem",
                color: "#a1a1aa",
                lineHeight: 1.5,
              }}
            >
              페이지 전체를 다시 불러오면 해결될 수 있습니다. 문제가 계속되면
              잠시 후 다시 시도해 주세요.
            </p>
          </div>

          {/* digest는 서버 로그와 대조 가능한 식별자라 노출한다(에러 원문은 감춘다) */}
          {error.digest && (
            <p
              style={{
                margin: 0,
                fontSize: "0.6875rem",
                fontFamily: "monospace",
                color: "#71717a",
                wordBreak: "break-all",
              }}
            >
              오류 코드: {error.digest}
            </p>
          )}

          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={() => unstable_retry()}
              style={{
                flex: 1,
                padding: "0.625rem",
                borderRadius: "0.75rem",
                border: "none",
                background: "#4f46e5",
                color: "#fff",
                fontSize: "0.875rem",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              다시 시도
            </button>
            {/* next/link 대신 전체 새로고침을 쓴다: global-error는 크래시한 루트
                레이아웃을 대체 중이라, 클라이언트 네비게이션(Link)이 아닌 하드
                리로드로 앱 전체를 재마운트해야 정상 복구된다. */}
            <button
              onClick={() => {
                window.location.href = "/";
              }}
              style={{
                flex: 1,
                padding: "0.625rem",
                borderRadius: "0.75rem",
                border: "none",
                background: "#27272a",
                color: "#fff",
                fontSize: "0.875rem",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              대시보드
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

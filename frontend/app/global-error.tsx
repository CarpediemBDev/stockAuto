"use client"; // 에러 바운더리는 반드시 클라이언트 컴포넌트여야 한다(Next.js 규약)

import React, { useEffect, useState } from "react";

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
 *
 * 다국어: 이 컴포넌트는 NextIntlClientProvider 바깥에서 렌더되므로 useTranslations를
 * 쓸 수 없다(넣으면 에러 화면 자체가 크래시). 자립 원칙에 맞춰 5개 문구만 인라인
 * 딕셔너리로 들고, 첫 렌더는 SSR과 동일하게 ko로 확정한 뒤 마운트 후 NEXT_LOCALE
 * 쿠키를 읽어 갱신한다(하이드레이션 불일치 회피). 쿠키가 없으면 브라우저 언어로 폴백.
 */
const MESSAGES = {
  ko: {
    docTitle: "오류 - StockAuto",
    heading: "앱을 불러오는 중 심각한 오류가 발생했습니다",
    body: "페이지 전체를 다시 불러오면 해결될 수 있습니다. 문제가 계속되면 잠시 후 다시 시도해 주세요.",
    errorCode: "오류 코드",
    retry: "다시 시도",
    dashboard: "대시보드",
  },
  en: {
    docTitle: "Error - StockAuto",
    heading: "A critical error occurred while loading the app",
    body: "Reloading the whole page may fix it. If the problem persists, please try again shortly.",
    errorCode: "Error code",
    retry: "Try again",
    dashboard: "Dashboard",
  },
} as const;

type Locale = keyof typeof MESSAGES;

function detectLocale(): Locale {
  if (typeof document === "undefined") return "ko"; // SSR 기본값
  const cookie = document.cookie.match(/(?:^|;\s*)NEXT_LOCALE=([^;]+)/);
  const fromCookie = cookie?.[1];
  if (fromCookie === "en" || fromCookie === "ko") return fromCookie;
  return navigator.language?.toLowerCase().includes("ko") ? "ko" : "en";
}

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  // SSR과 첫 클라이언트 렌더는 항상 ko로 일치시켜 하이드레이션 불일치를 막고,
  // 마운트 직후 쿠키/브라우저 언어로 갱신한다.
  const [locale, setLocale] = useState<Locale>("ko");
  const t = MESSAGES[locale];

  useEffect(() => {
    console.error("[GlobalError:root]", error);
  }, [error]);

  useEffect(() => {
    // NavBar와 동일: 하이드레이션 불일치를 피하려 SSR은 ko로 확정하고 마운트 후 실제
    // 로케일로 갱신한다. 이 규칙이 막는 렌더 중 setState가 아니라 마운트 1회 갱신이다.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocale(detectLocale());
  }, []);

  return (
    // global-error는 <html>/<body>를 직접 포함해야 한다(루트 레이아웃 대체)
    <html lang={locale}>
      <title>{t.docTitle}</title>
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
              {t.heading}
            </h2>
            <p
              style={{
                margin: "0.375rem 0 0",
                fontSize: "0.75rem",
                color: "#a1a1aa",
                lineHeight: 1.5,
              }}
            >
              {t.body}
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
              {t.errorCode}: {error.digest}
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
              {t.retry}
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
              {t.dashboard}
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

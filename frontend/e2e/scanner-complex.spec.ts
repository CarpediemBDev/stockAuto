import { expect, test } from "@playwright/test";

test("Mocked Overseas Scanner & Swing Predictor Magic Show", async ({ page }) => {
  // 1. 모의(Mocking) 백엔드 응답 설정
  // 프론트엔드가 백엔드를 호출할 때 실제 백엔드를 타지 않고,
  // Playwright가 가짜 데이터(Mock Data)를 즉시 던져주도록 설정합니다.

  // 1-1. 가짜 로그인 토큰 발급
  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: {
          access_token: "fake_magic_token",
          refresh_token: "fake_magic_refresh_token",
          token_type: "bearer",
          username: "MagicUser",
        },
      },
    });
  });

  // 1-2. 전체 페이지 이동 후 HttpOnly refresh 기반 세션 복구
  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: {
          access_token: "fake_magic_token_refreshed",
          token_type: "bearer",
          username: "MagicUser",
        },
      },
    });
  });

  // 1-3. 가짜 내 정보 응답
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: { username: "MagicUser", is_active: true },
      },
    });
  });

  // 1-4. 스캐너 초기 목록 (마켓 스캐너)
  await page.route("**/api/v1/scanner/latest", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: [
          {
            ticker: "NVDA", name: "엔비디아", price: 1200.5, signal_score: 98, signal_type: "STRONG_BUY",
            details: { gap: 2.5, rvol: 3.1, wick: 0.1, has_news: true, risk: "LOW", rs: 5.2, ema_aligned: true }
          },
          {
            ticker: "TSLA", name: "테슬라", price: 180.2, signal_score: 85, signal_type: "BUY",
            details: { gap: 1.2, rvol: 1.5, wick: 0.2, has_news: false, risk: "MEDIUM", rs: 2.1, ema_aligned: true }
          },
        ],
      },
    });
  });

  // 1-5. 스윙 예측 갱신 API (수동 스캔 클릭 시)
  await page.route("**/api/v1/scanner/swing-predict/refresh", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: {
          sync_status: "refreshing",
          updated_at: new Date().toISOString(),
          candidates: [
            {
              ticker: "MSFT", name: "마이크로소프트", price: 410.0, score: 92, signal_type: "STRONG_BUY",
              vcp_triggered: true, vud_ratio: 0.3, squeeze_pct: 15.0, obv_divergence: 12.0, close: 410.0, change_pct: 1.5, is_bullish_trend: true
            },
            {
              ticker: "AAPL", name: "애플", price: 190.0, score: 88, signal_type: "BUY",
              vcp_triggered: false, vud_ratio: 0.6, squeeze_pct: 25.0, obv_divergence: 5.0, close: 190.0, change_pct: -0.5, is_bullish_trend: true
            }
          ]
        }
      },
    });
  });

  // 1-6. 스윙 예측 리스트 (폴링으로 가져올 때)
  await page.route("**/api/v1/scanner/swing-predict", async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        code: "SUCCESS",
        data: {
          sync_status: "fresh",
          updated_at: new Date().toISOString(),
          candidates: [
            {
              ticker: "MSFT", name: "마이크로소프트", price: 410.0, score: 92, signal_type: "STRONG_BUY",
              vcp_triggered: true, vud_ratio: 0.3, squeeze_pct: 15.0, obv_divergence: 12.0, close: 410.0, change_pct: 1.5, is_bullish_trend: true
            },
            {
              ticker: "AAPL", name: "애플", price: 190.0, score: 88, signal_type: "BUY",
              vcp_triggered: false, vud_ratio: 0.6, squeeze_pct: 25.0, obv_divergence: 5.0, close: 190.0, change_pct: -0.5, is_bullish_trend: true
            }
          ]
        },
      },
    });
  });

  // 2. 본격적인 마법 쇼 (UI 자동 조종 시작)

  // 2-1. 로그인 페이지 접속
  await page.goto("/login");
  await page.waitForTimeout(500); // 💡 마술 쇼 관람을 위한 의도적 지연 (실무 테스트엔 넣지 않음)

  // 2-2. 폼 채우고 로그인
  await page.getByPlaceholder("Username").fill("MagicUser");
  await page.getByPlaceholder("Password").fill("supersecret");
  await page.waitForTimeout(500);

  // 로그인 버튼 클릭! (여기서 1-1 가짜 토큰을 받음)
  await page.getByRole("button", { name: "로그인" }).click();

  // 홈 화면으로 리다이렉트 되었는지 확인
  await expect(page).toHaveURL("/");
  await page.waitForTimeout(500);

  // 2-3. 네비게이션을 통해 "스캐너" 페이지로 강제 이동
  await page.goto("/scanner");

  // 마켓 스캐너 탭에 모킹해둔 엔비디아, 테슬라가 보이는지 확인
  await expect(page.getByText("엔비디아")).toBeVisible();
  await expect(page.getByText("테슬라")).toBeVisible();
  await page.waitForTimeout(1000);

  // 2-4. '스윙' 탭 클릭
  await page.getByRole("button", { name: /스윙/i }).click();
  await page.waitForTimeout(1000);

  // 2-5. '수동 갱신' 버튼 클릭
  const refreshButton = page.getByRole("button", { name: "수동 갱신" });
  await expect(refreshButton).toBeVisible();
  await refreshButton.click();

  // 2-6. 토스트 알림 검증 (우측 하단에 뜨는지)
  await expect(page.getByText(/백그라운드에서 시작/)).toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(1500);

  // 2-7. 스윙 예측 결과물 (마이크로소프트, 애플) 렌더링 확인
  await expect(page.getByText("MSFT")).toBeVisible();
  await expect(page.getByText("AAPL")).toBeVisible();

  // 여운을 위한 마지막 대기
  await page.waitForTimeout(2000);
});

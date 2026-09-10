import { expect, test, type Route } from "@playwright/test";

// 화면이 시각을 뷰어의 타임존으로 찍으므로 날짜 단언이 실행 머신에 좌우된다. 고정한다.
test.use({ timezoneId: "Asia/Seoul" });

/**
 * 포트폴리오 카드 → 종목별 체결 이력 모달의 배선 회귀 테스트.
 *
 * 고정하는 계약은 세 가지다.
 *  1. 클릭이 서버에 티커를 실어 보낸다. 전체 목록을 받아 화면에서 거르면 거래가 잦은
 *     종목들에 밀려 조용한 보유분의 매수 기록이 응답 창 밖으로 나간다(백엔드 계약은
 *     docs/API_STANDARD.md 7절, 단위 회귀는 backend/tests/test_trade_log_ticker_filter.py).
 *  2. 매수 시각·체결가가 실제로 렌더된다. 이 화면의 존재 이유가 그 두 값이다.
 *  3. 팔았다 다시 산 종목의 "보유 시작"은 마지막 재진입 시점이다. 첫 매수로 표시하면
 *     이미 청산된 포지션의 날짜를 현재 보유분의 것으로 읽게 된다.
 */

const HOLDING = {
  id: 1,
  ticker: "QLD",
  ticker_name: "프로셰어즈 울트라 QQQ",
  avg_price: 100,
  quantity: 10,
  highest_price: 130,
  current_price: 120,
  fx_rate: 1350,
  is_mock: true,
  provider: "Simulated",
  strategy_type: "leveraged_regime",
  strategy_name: "레버리지 레짐",
  management: "BOT_OWNED",
  slices: [{ strategy_type: "leveraged_regime", management: "BOT_OWNED", quantity: 10 }],
};

// 최신순(서버가 executed_at DESC로 준다). 중간의 전량 매도가 포지션을 한 번 닫으므로
// 현재 보유분의 시작은 그 뒤의 매수(2026-03-02)여야 한다.
const QLD_LOGS = [
  {
    id: 4, ticker: "QLD", ticker_name: "프로셰어즈 울트라 QQQ", trade_type: "BUY",
    price: 110.5, quantity: 4, executed_at: "2026-03-05T14:30:00+00:00",
    strategy_type: "leveraged_regime", signal_score: 72,
  },
  {
    id: 3, ticker: "QLD", ticker_name: "프로셰어즈 울트라 QQQ", trade_type: "BUY",
    price: 96.0, quantity: 6, executed_at: "2026-03-02T14:30:00+00:00",
    strategy_type: "leveraged_regime", signal_score: 88,
  },
  {
    id: 2, ticker: "QLD", ticker_name: "프로셰어즈 울트라 QQQ", trade_type: "SELL",
    price: 80.0, quantity: 5, executed_at: "2026-01-20T14:30:00+00:00",
    strategy_type: "leveraged_regime", realized_pnl: -50.0, return_rate: -11.11,
  },
  {
    id: 1, ticker: "QLD", ticker_name: "프로셰어즈 울트라 QQQ", trade_type: "BUY",
    price: 90.0, quantity: 5, executed_at: "2026-01-10T14:30:00+00:00",
    strategy_type: "leveraged_regime", signal_score: 64,
  },
];

test("포트폴리오 종목을 누르면 그 종목의 체결 이력만 조회해 보여준다", async ({ page }) => {
  const tradeRequestUrls: string[] = [];
  let sessionActive = false;

  const ok = (route: Route, data: unknown) =>
    route.fulfill({ status: 200, json: { code: "SUCCESS", data } });

  await page.route("**/api/v1/auth/login", async (route) => {
    sessionActive = true;
    await ok(route, {
      access_token: "history-token",
      token_type: "bearer",
      username: "HistoryUser",
      role: "USER",
    });
  });
  await page.route("**/api/v1/auth/refresh", async (route) => {
    if (!sessionActive) {
      await route.fulfill({ status: 401, json: { detail: "No refresh session" } });
      return;
    }
    await ok(route, {
      access_token: "history-token-refreshed",
      token_type: "bearer",
      username: "HistoryUser",
      role: "USER",
    });
  });
  await page.route("**/api/v1/auth/me", (route) => ok(route, { username: "HistoryUser", is_active: true }));
  await page.route("**/api/v1/bot/status", (route) => ok(route, { is_running: false, is_real: false }));
  await page.route("**/api/v1/account/balance", (route) =>
    ok(route, {
      total_asset: 1200,
      cash_balance: 0,
      stock_balance: 1200,
      profit_rate: 20,
      fx_rate: 1350,
      focused_radar_tickers: [],
    }),
  );
  await page.route("**/api/v1/account/holdings", (route) => ok(route, [HOLDING]));
  await page.route("**/api/v1/scanner/latest", (route) => ok(route, []));
  await page.route("**/api/v1/market/overview", (route) =>
    ok(route, { market_condition: "NEUTRAL", sentiment: "NEUTRAL", nasdaq: null, exchange_rate: null }),
  );
  await page.route("**/api/v1/strategies/catalog", (route) => ok(route, []));
  // 모킹하지 않으면 실제 로컬 백엔드(BACKEND_API_ORIGIN)로 새어 나가 결과가 머신 상태에 좌우된다.
  await page.route("**/api/v1/admin", (route) =>
    ok(route, { trade_mode: "SIMULATED", strategy_type: "leveraged_regime" }),
  );

  // 대시보드의 전체 로그 호출과 모달의 종목별 호출이 같은 경로를 쓴다. 쿼리로 갈라
  // 서버가 필터를 받았는지(=클라이언트가 티커를 실어 보냈는지)를 여기서 확인한다.
  await page.route("**/api/v1/trades**", (route) => {
    const url = route.request().url();
    tradeRequestUrls.push(url);
    const ticker = new URL(url).searchParams.get("ticker");
    if (!ticker) return ok(route, []);
    return ok(route, ticker === "QLD" ? QLD_LOGS : []);
  });

  await page.goto("/login");
  await page.locator('input[name="username"]').fill("HistoryUser");
  await page.locator('input[name="password"]').fill("supersecret");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL("/");

  const tickerButton = page.getByRole("button", { name: /QLD/ }).first();
  await expect(tickerButton).toBeVisible();
  await tickerButton.click();

  // 1. 서버에 티커가 실려 나갔다.
  await expect
    .poll(() => tradeRequestUrls.some((url) => url.includes("ticker=QLD")))
    .toBe(true);

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("프로셰어즈 울트라 QQQ").first()).toBeVisible();

  // 2. 매수 시각과 체결가가 렌더된다. 표시 통화 기본값은 원화이므로 환산 금액으로 확인한다
  //    (96 × 1350 = 129,600). 반올림 경계에 단언을 걸지 않으려고 떨어지는 값을 골랐다.
  await expect(dialog.getByText("₩129,600").first()).toBeVisible();
  await expect(dialog.getByText(/2026\. 3\. 2\./).first()).toBeVisible();
  await expect(dialog.getByText("매수 3건 · 매도 1건")).toBeVisible();

  // 3. 보유 시작은 전량 매도 이후의 재진입 시점이다. 첫 매수(2026-01-10)가 아니다.
  const openedAt = dialog.getByText("보유 시작").locator("xpath=following-sibling::*[1]");
  await expect(openedAt).toContainText("2026. 3. 2.");
  await expect(openedAt).not.toContainText("2026. 1. 10.");

  // 매도 행의 실현손익은 손실 색·부호를 그대로 싣는다.
  await expect(dialog.getByText(/-₩67,500/)).toBeVisible();
});

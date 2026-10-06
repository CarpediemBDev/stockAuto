import { expect, test, type Page, type Route } from "@playwright/test";

// 화면이 시각을 뷰어의 타임존으로 찍으므로 날짜 단언이 실행 머신에 좌우된다. 고정한다.
test.use({ timezoneId: "Asia/Seoul" });

/**
 * 포트폴리오 카드 → 종목별 체결 이력 모달·종목 정보 모달의 배선 회귀 테스트.
 *
 * 진입점은 둘로 나뉜다: "매수 이력" 버튼은 체결 이력, 종목명·코드는 종목 정보(점수·뉴스·기준선).
 * 이력 모달에서 고정하는 계약은 네 가지다.
 *  0. 이력 범위는 카드 단위와 같다. 같은 종목 카드가 둘 이상(슬라이스 단위)일 때만 전략으로 좁힌다.
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

type Mocks = { holdings: unknown[]; signals?: unknown[] };

/** 로그인부터 대시보드 진입까지. 화면이 보낸 /trades 요청 URL을 모아 돌려준다. */
async function openDashboard(page: Page, { holdings, signals = [] }: Mocks) {
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
  await page.route("**/api/v1/account/holdings", (route) => ok(route, holdings));
  await page.route("**/api/v1/scanner/latest", (route) => ok(route, { is_scanning: false, signals }));
  await page.route("**/api/v1/market/overview", (route) =>
    ok(route, { market_condition: "NEUTRAL", sentiment: "NEUTRAL", nasdaq: null, exchange_rate: null }),
  );
  await page.route("**/api/v1/strategies/catalog", (route) => ok(route, []));
  // 모킹하지 않으면 실제 로컬 백엔드(BACKEND_API_ORIGIN)로 새어 나가 결과가 머신 상태에 좌우된다.
  await page.route("**/api/v1/admin", (route) =>
    ok(route, { trade_mode: "SIMULATED", strategy_type: "leveraged_regime" }),
  );

  // 대시보드의 전체 로그 호출과 모달의 종목별 호출이 같은 경로를 쓴다. 쿼리로 갈라
  // 서버가 필터를 받았는지(=클라이언트가 티커·전략을 실어 보냈는지)를 여기서 확인한다.
  await page.route("**/api/v1/trades**", (route) => {
    const url = route.request().url();
    tradeRequestUrls.push(url);
    const params = new URL(url).searchParams;
    const ticker = params.get("ticker");
    if (!ticker) return ok(route, []);
    const strategy = params.get("strategy_type");
    const logs = ticker === "QLD" ? QLD_LOGS : [];
    return ok(route, strategy ? logs.filter((log) => log.strategy_type === strategy) : logs);
  });

  await page.goto("/login");
  await page.locator('input[name="username"]').fill("HistoryUser");
  await page.locator('input[name="password"]').fill("supersecret");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL("/");
  return tradeRequestUrls;
}

const tickerHistoryUrls = (urls: string[]) => urls.filter((url) => url.includes("ticker="));

test("매수 이력 버튼을 누르면 그 종목의 체결 이력만 조회해 보여준다", async ({ page }) => {
  const tradeRequestUrls = await openDashboard(page, { holdings: [HOLDING] });

  await page.getByRole("button", { name: "매수 이력" }).click();

  // 1. 서버에 티커가 실려 나갔다. 카드가 한 장뿐이므로 전략으로 좁히지 않는다 -
  //    KIS·Toss의 합쳐진 카드에서 좁히면 다른 슬라이스 체결이 빠진다(API_STANDARD 7절).
  await expect
    .poll(() => tickerHistoryUrls(tradeRequestUrls).some((url) => url.includes("ticker=QLD")))
    .toBe(true);
  expect(tickerHistoryUrls(tradeRequestUrls).every((url) => !url.includes("strategy_type="))).toBe(true);

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

test("같은 종목을 두 전략이 나눠 들면 카드의 전략 슬라이스 체결만 보여준다", async ({ page }) => {
  // SIMULATED는 슬라이스마다 카드가 한 장이다. 요약(평단가·수량)은 그 슬라이스 몫이므로
  // 체결 목록도 같은 범위여야 대조가 된다. 예전에는 두 전략의 체결이 합쳐져 나왔다.
  const benchmarkSlice = {
    ...HOLDING,
    quantity: 3,
    avg_price: 150,
    strategy_type: "benchmark",
    strategy_name: "벤치마크",
  };
  const tradeRequestUrls = await openDashboard(page, { holdings: [HOLDING, benchmarkSlice] });

  await page.getByRole("button", { name: "매수 이력" }).nth(1).click();

  await expect
    .poll(() => tickerHistoryUrls(tradeRequestUrls).some((url) => url.includes("strategy_type=benchmark")))
    .toBe(true);
  const dialog = page.getByRole("dialog");
  // 목데이터의 QLD 체결은 전부 leveraged_regime이다. 범위가 맞으면 이 슬라이스의 이력은 비어 있다.
  await expect(dialog.getByText("이 종목의 체결 기록이 없습니다")).toBeVisible();
  await expect(dialog.getByText("매수 3건 · 매도 1건")).toHaveCount(0);
});

test("종목명을 누르면 체결 이력이 아니라 종목 정보를 보여준다", async ({ page }) => {
  const tradeRequestUrls = await openDashboard(page, { holdings: [HOLDING] });

  await page.getByRole("button", { name: "프로셰어즈 울트라 QQQ" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("가격 기준선")).toBeVisible();
  // 현재가 120, 평단가 100 → 평단가에서 본 현재가 +20.00%. 고점 130에서 본 현재가 -7.69%.
  await expect(dialog.getByText("현재가 +20.00%")).toBeVisible();
  await expect(dialog.getByText("현재가 -7.69%")).toBeVisible();
  // 스캐너 응답에 없는 종목은 빈 칸이 아니라 이유를 밝힌다.
  await expect(dialog.getByText("최근 스캔 결과에 없는 종목입니다")).toBeVisible();
  // 이력 조회는 일어나지 않는다.
  expect(tickerHistoryUrls(tradeRequestUrls)).toHaveLength(0);
});

test("스캔 결과에 있는 보유 종목은 점수와 뉴스를 함께 보여준다", async ({ page }) => {
  await openDashboard(page, {
    holdings: [HOLDING],
    signals: [
      {
        ticker: "QLD",
        name: "프로셰어즈 울트라 QQQ",
        price: 120,
        signal_score: 73,
        signal_type: "BUY",
        score_card: [
          { factor: "EMA 정배열", score: 20, passed: true },
          { factor: "거래량 급증", score: 15, passed: false },
        ],
        news_sentiment: "POSITIVE",
        news_sentiment_score: 68,
        news_summary: "나스닥 반등 기대감에 레버리지 ETF 자금 유입",
        details: { gap: 0, rvol: 1, wick: 0, has_news: true, risk: "LOW", rs: 0, ema_aligned: true },
      },
    ],
  });

  // 카드의 코드 버튼도 같은 모달을 연다.
  await page.getByRole("button", { name: "QLD", exact: true }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("스캐너 점수")).toBeVisible();
  await expect(dialog.getByText("EMA 정배열")).toBeVisible();
  await expect(dialog.getByText("통과 1 / 전체 2 항목")).toBeVisible();
  await expect(dialog.getByText("나스닥 반등 기대감에 레버리지 ETF 자금 유입")).toBeVisible();
  await expect(dialog.getByText("최근 스캔 결과에 없는 종목입니다")).toHaveCount(0);
});

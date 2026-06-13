import { expect, test, type Route } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      status: 401,
      json: { detail: "No refresh session" },
    });
  });
});

test("localhost visits remain on the localhost host", async ({ page }) => {
  await page.goto("http://localhost:3100/login");

  await expect(page).toHaveURL("http://localhost:3100/login");
});

test("anonymous root visits are redirected to the login screen", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "StockAuto 로그인" })).toBeVisible();
  await expect(page.getByPlaceholder("Username")).toBeVisible();
  await expect(page.getByPlaceholder("Password")).toBeVisible();
});

test("login and signup pages navigate without backend calls", async ({ page }) => {
  await page.goto("/login");

  await page.getByRole("link", { name: "무료 회원가입" }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("heading", { name: "StockAuto 회원가입" })).toBeVisible();
  await expect(page.getByPlaceholder("Confirm Password")).toBeVisible();

  await page.getByRole("link", { name: "로그인하기" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "StockAuto 로그인" })).toBeVisible();
});

test("empty login submission shows client-side validation", async ({ page }) => {
  await page.goto("/login");

  await page.getByRole("button", { name: "로그인" }).click();

  await expect(page.getByText("아이디와 비밀번호를 모두 입력해 주세요.")).toBeVisible();
});

test("HttpOnly refresh cookie survives different local ports and reload", async ({ page }) => {
  await page.unroute("**/api/v1/auth/refresh");
  let refreshSawCookie = false;
  let refreshRequestCount = 0;

  const fulfillSuccess = async (route: Route, data: unknown) => {
    await route.fulfill({
      status: 200,
      json: { code: "SUCCESS", data },
    });
  };

  const fulfillProtected = async (route: Route, data: unknown) => {
    const isAuthorized =
      route.request().headers()["authorization"] === "Bearer refreshed-access-token";
    if (!isAuthorized) {
      await route.fulfill({
        status: 401,
        json: { detail: "Expired access token" },
      });
      return;
    }
    await fulfillSuccess(route, data);
  };

  await page.route("**/api/v1/bot/status", (route) =>
    fulfillProtected(route, { is_running: false, is_real: false }),
  );
  await page.route("**/api/v1/trades", (route) => fulfillProtected(route, []));
  await page.route("**/api/v1/account/balance", (route) =>
    fulfillSuccess(route, {
      total_asset: 0,
      cash_balance: 0,
      stock_balance: 0,
      profit_rate: 0,
      fx_rate: 1350,
      focused_radar_tickers: [],
    }),
  );
  await page.route("**/api/v1/account/holdings", (route) => fulfillSuccess(route, []));
  await page.route("**/api/v1/scanner/latest", (route) => fulfillSuccess(route, []));
  await page.route("**/api/v1/market/overview", (route) =>
    fulfillSuccess(route, {
      market_condition: "NEUTRAL",
      sentiment: "NEUTRAL",
      nasdaq: null,
      exchange_rate: null,
    }),
  );

  await page.route("**/api/v1/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "set-cookie": "refresh_token=port-safe-cookie; Path=/api/v1/auth; HttpOnly; SameSite=Lax",
      },
      json: {
        access_token: "initial-access-token",
        token_type: "bearer",
        username: "cookie-user",
        role: "USER",
      },
    });
  });

  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshRequestCount += 1;
    refreshSawCookie = route.request().headers()["cookie"]?.includes("port-safe-cookie") ?? false;
    await route.fulfill({
      status: refreshSawCookie ? 200 : 401,
      headers: refreshSawCookie
        ? {
            "set-cookie": "refresh_token=rotated-port-safe-cookie; Path=/api/v1/auth; HttpOnly; SameSite=Lax",
          }
        : undefined,
      json: refreshSawCookie
        ? {
            access_token: "refreshed-access-token",
            token_type: "bearer",
            username: "cookie-user",
            role: "USER",
          }
        : { detail: "Refresh cookie missing" },
    });
  });

  await page.goto("/login");
  await expect.poll(() => refreshRequestCount).toBe(1);
  refreshRequestCount = 0;
  refreshSawCookie = false;
  await page.getByPlaceholder("Username").fill("cookie-user");
  await page.getByPlaceholder("Password").fill("long-enough-password");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL("/");
  await expect.poll(() => refreshRequestCount).toBe(1);
  expect(refreshSawCookie).toBe(true);

  refreshRequestCount = 0;
  await page.reload();
  await expect(page).toHaveURL("/");
  expect(refreshSawCookie).toBe(true);
  expect(refreshRequestCount).toBe(1);
});

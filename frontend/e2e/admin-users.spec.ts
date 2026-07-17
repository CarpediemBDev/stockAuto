import { expect, test } from "@playwright/test";

test.describe("Admin User Management Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    // Mock login and auth state
    await page.route("**/api/v1/auth/login", async (route) => {
      await route.fulfill({
        status: 200,
        json: { code: "SUCCESS", data: { access_token: "test-token", username: "admin", role: "ADMIN" } },
      });
    });

    await page.route("**/api/v1/auth/refresh", async (route) => {
      await route.fulfill({
        status: 200,
        json: { code: "SUCCESS", data: { access_token: "test-token", username: "admin", role: "ADMIN" } },
      });
    });

    await page.route("**/api/v1/bot/status", async (route) => {
      await route.fulfill({ status: 200, json: { code: "SUCCESS", data: { is_running: false } } });
    });
    
    await page.route("**/api/v1/market/overview", async (route) => {
      await route.fulfill({ status: 200, json: { code: "SUCCESS", data: { market_condition: "NEUTRAL" } } });
    });

    // Mock the users list API that was causing issues
    await page.route("**/api/v1/admin/users", async (route) => {
      await route.fulfill({
        status: 200,
        json: [
          {
            id: 1,
            username: "testuser",
            role: "USER",
            trade_mode: "MOCK",
            is_running: true,
            profit_rate: null,
            strategy_type: "senior_simple",
            credentials: [],
          },
          {
            id: 2,
            username: "testuser2",
            role: "USER",
            trade_mode: "REAL",
            is_running: false,
            profit_rate: "12.34",
            strategy_type: "turtle_trading",
            credentials: [],
          },
          {
            id: 3,
            username: "obs_qqq_hold",
            role: "USER",
            trade_mode: "SIMULATED",
            is_running: true,
            profit_rate: 3.45,
            strategy_type: "benchmark_qqq_hold",
            credentials: [],
          }
        ],
      });
    });
  });

  test("should render the total user management screen without crashing", async ({ page }) => {
    await page.goto("/admin");

    const userTab = page.locator('button', { hasText: '전체 사용자 관리' });
    await userTab.waitFor({ state: "visible" });
    await userTab.click();

    const tableRow = page.locator('td', { hasText: 'testuser' }).first();
    await expect(tableRow).toBeVisible();

    await expect(page.locator('td:has-text("-")').first()).toBeVisible();
    await expect(page.locator('td:has-text("12.34%")').first()).toBeVisible();

    // Verify that the observation account (obs_qqq_hold) renders the "EXEMPT" badge
    const exemptBadge = page.locator('tr:has-text("obs_qqq_hold")').locator('span:has-text("EXEMPT")');
    await expect(exemptBadge).toBeVisible();
  });
});

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
        // Using an array response to mock the backend
        json: [
          {
            id: 1,
            username: "testuser",
            role: "USER",
            trade_mode: "MOCK",
            is_running: true,
            profit_rate: null, // Edge case that previously caused the crash!
            strategy_type: "senior_simple",
            credentials: [],
            equity_curve: [],
          },
          {
            id: 2,
            username: "testuser2",
            role: "USER",
            trade_mode: "REAL",
            is_running: false,
            profit_rate: "12.34", // Edge case: string instead of number
            strategy_type: "turtle_trading",
            credentials: [],
            equity_curve: [],
          }
        ],
      });
    });
  });

  test("should render the total user management screen without crashing", async ({ page }) => {
    // Perform mock login to initialize Zustand store properly
    await page.goto("/login");
    await page.fill('input[type="text"]', "admin");
    await page.fill('input[type="password"]', "admin");
    await page.click('button[type="submit"]');
    await page.waitForURL("**/");

    // Mock Next.js router injecting state
    await page.goto("/admin");

    // Click the users management menu tab
    const userTab = page.locator('button', { hasText: '전체 사용자 관리' });
    await userTab.waitFor({ state: "visible" });
    await userTab.click();

    // Verify the page actually renders the table and doesn't white-screen
    // Wait for the "testuser" to appear in the table
    const tableRow = page.locator('td', { hasText: 'testuser' }).first();
    await expect(tableRow).toBeVisible();

    // Verify that the profit rate edge cases rendered correctly instead of crashing
    // For profit_rate: null, it should render "-"
    await expect(page.locator('td:has-text("-")').first()).toBeVisible();
    
    // For profit_rate: "12.34", it should correctly cast and render "12.34%"
    await expect(page.locator('td:has-text("12.34%")').first()).toBeVisible();
  });
});

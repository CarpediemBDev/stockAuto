import { expect, test } from "@playwright/test";

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

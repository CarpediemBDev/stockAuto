import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // i18n.ts는 NEXT_LOCALE 쿠키가 없으면 Accept-Language로 로케일을 정하고,
    // 한국어가 아니면 en으로 배정한다. Playwright 기본값은 en-US라 화면이 영어로
    // 렌더되어 한글 문구를 찾는 기존 단언들이 깨진다. 테스트가 전제하는 한국어 UI를
    // 결정적으로 고정하기 위해 로케일을 명시한다.
    locale: "ko-KR",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run build && npm run start:e2e",
    url: `${baseURL}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
    env: {
      NEXT_DIST_DIR: ".next-e2e",
      NEXT_PUBLIC_API_BASE: "/api/v1",
      BACKEND_API_ORIGIN: "http://127.0.0.1:8000",
      // E2E는 기존 플로우를 결정적으로 검증. SSE는 별도 통합 테스트로 검증하므로 여기선 끈다.
      NEXT_PUBLIC_SSE_ENABLED: "false",
    },
  },
});

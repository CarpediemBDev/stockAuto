import { defineConfig, devices } from "@playwright/test";

import { E2E_BASE_URL, E2E_HOST, E2E_PORT } from "./e2e/constants";

const baseURL = E2E_BASE_URL;

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
    // 2026-09-06 사고: 당시 E2E 포트였던 :3100에 다른 프로젝트(stock-auto-mobile)의 next dev 서버가
    // 떠 있었고, reuseExistingServer가 그 서버를 재사용해 빌드조차 하지 않은 채
    // 남의 앱을 검사했다(trailingSlash 차이로 auth-smoke 1건 실패). 재사용은
    // '옛 빌드로 조용히 통과'하는 경로도 함께 열어주므로 로컬에서도 금지한다.
    // 포트가 이미 점유돼 있으면 Playwright가 명시적으로 실패한다
    // (선점 정리는 scripts/verify_harness.py의 sweep_e2e_port가 먼저 수행한다).
    reuseExistingServer: false,
    timeout: 300_000,
    env: {
      // 서버가 붙는 주소는 baseURL과 반드시 같아야 한다. start-e2e-server.mjs의
      // 기본값에 기대지 않고 여기서 명시해 한 곳(e2e/constants.ts)만 보게 만든다.
      PORT: String(E2E_PORT),
      HOSTNAME: E2E_HOST,
      NEXT_DIST_DIR: ".next-e2e",
      NEXT_PUBLIC_API_BASE: "/api/v1",
      BACKEND_API_ORIGIN: "http://127.0.0.1:8000",
      // E2E는 기존 플로우를 결정적으로 검증. SSE는 별도 통합 테스트로 검증하므로 여기선 끈다.
      NEXT_PUBLIC_SSE_ENABLED: "false",
    },
  },
});

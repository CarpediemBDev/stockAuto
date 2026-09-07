/**
 * E2E 실행 포트/호스트의 TypeScript 단일 정의.
 *
 * playwright.config.ts(baseURL·webServer.env), e2e 스펙, 그리고
 * scripts/verify_harness.py(포트 관문·서버 회수)가 모두 같은 포트를 봐야 한다.
 * 파이썬은 이 파일을 import 할 수 없으므로 verify_harness.py의 E2E_PORT가
 * 값을 복제하고, check_e2e_port_alignment가 여기 적힌 값과 대조해 어긋나면
 * E2E를 시작하기 전에 실패시킨다. 포트를 옮길 때는 이 파일과 그 상수를 함께 고친다.
 *
 * 3100을 쓰지 않는 이유: 같은 머신의 다른 프로젝트(stock-auto-mobile)의 개발 서버가
 * 그 포트를 상시 점유해 2026-09-06에 하네스가 남의 앱을 검사하는 사고가 났다.
 * 이 저장소가 이미 쓰는 8000(백엔드)·3000(프론트 로컬)·6379(Redis)와도 겹치지 않는
 * 값으로 옮겼다.
 *
 * testMatch 기본 패턴(*.spec.ts)에 걸리지 않으므로 이 파일은 테스트로 수집되지 않는다.
 */
export const E2E_PORT = 3510;

/** Playwright가 접속하는 기본 호스트. 서버도 이 주소에 바인딩한다. */
export const E2E_HOST = "127.0.0.1";

export const E2E_BASE_URL = `http://${E2E_HOST}:${E2E_PORT}`;

/**
 * 같은 서버를 127.0.0.1이 아닌 localhost 이름으로 가리키는 주소.
 * 호스트 이름이 바뀌어도 앱이 다른 호스트로 튕기지 않는지 검증하는 데 쓴다.
 */
export const E2E_LOCALHOST_BASE_URL = `http://localhost:${E2E_PORT}`;

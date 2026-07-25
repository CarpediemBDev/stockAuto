import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

process.env.PORT ||= "3100";
process.env.HOSTNAME ||= "127.0.0.1";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "..");
const distDir = process.env.NEXT_DIST_DIR || ".next-e2e";
const distRoot = path.join(frontendRoot, distDir);
const standaloneRoot = path.join(distRoot, "standalone");

// standalone 산출물에서 server.js가 놓이는 위치는 Turbopack 루트 설정에 따라 달라진다.
// 루트가 frontend면 standalone/server.js, 저장소 루트면 루트 기준 상대 경로가 보존되어
// standalone/frontend/server.js가 된다. 어느 쪽이든 동작하도록 실제 위치를 찾는다.
const candidates = [
  standaloneRoot,
  path.join(standaloneRoot, path.basename(frontendRoot)),
];
const appRoot = candidates.find((dir) => fs.existsSync(path.join(dir, "server.js")));
if (!appRoot) {
  throw new Error(
    `standalone server.js를 찾지 못했습니다. 확인한 경로: ${candidates.join(", ")}`,
  );
}

const staticSource = path.join(distRoot, "static");
const staticTarget = path.join(appRoot, distDir, "static");
if (fs.existsSync(staticSource)) {
  fs.cpSync(staticSource, staticTarget, { recursive: true, force: true });
}

const publicSource = path.join(frontendRoot, "public");
const publicTarget = path.join(appRoot, "public");
if (fs.existsSync(publicSource)) {
  fs.cpSync(publicSource, publicTarget, { recursive: true, force: true });
}

// next-intl(i18n.ts)은 런타임에 process.cwd()/../locales/<locale>.json 을 읽는다.
// standalone server.js 는 기동 시 process.chdir(appRoot) 를 수행하므로 조회 경로는
// resolve(appRoot, "..")/locales 가 된다(appRoot 가 standalone 이든 standalone/frontend 이든 동일 규칙).
// standalone 빌드는 저장소 루트 locales/ 를 산출물에 포함하지 않아 ENOENT → 번역 로딩 실패
// → 렌더 깨짐(플레이크)이 발생하므로, 서버 기동 직전에 루트 locales/ 를 그 경로로 복사한다.
const repoRoot = path.resolve(frontendRoot, "..");
const localesSource = path.join(repoRoot, "locales");
const localesTarget = path.join(path.resolve(appRoot, ".."), "locales");
if (fs.existsSync(localesSource)) {
  fs.cpSync(localesSource, localesTarget, { recursive: true, force: true });
} else {
  throw new Error(
    `[start-e2e-server] locales source not found: ${localesSource}. ` +
      "E2E 렌더가 번역 없이 깨지므로 기동을 중단한다.",
  );
}

await import(pathToFileURL(path.join(appRoot, "server.js")).href);

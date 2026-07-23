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

await import(pathToFileURL(path.join(appRoot, "server.js")).href);

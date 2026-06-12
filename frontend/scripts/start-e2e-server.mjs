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

const staticSource = path.join(distRoot, "static");
const staticTarget = path.join(standaloneRoot, distDir, "static");
if (fs.existsSync(staticSource)) {
  fs.cpSync(staticSource, staticTarget, { recursive: true, force: true });
}

const publicSource = path.join(frontendRoot, "public");
const publicTarget = path.join(standaloneRoot, "public");
if (fs.existsSync(publicSource)) {
  fs.cpSync(publicSource, publicTarget, { recursive: true, force: true });
}

await import(pathToFileURL(path.join(standaloneRoot, "server.js")).href);

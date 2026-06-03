import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

process.env.PORT ||= "3100";
process.env.HOSTNAME ||= "127.0.0.1";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "..");
const standaloneRoot = path.join(frontendRoot, ".next", "standalone");

const staticSource = path.join(frontendRoot, ".next", "static");
const staticTarget = path.join(standaloneRoot, ".next", "static");
if (fs.existsSync(staticSource)) {
  fs.cpSync(staticSource, staticTarget, { recursive: true, force: true });
}

const publicSource = path.join(frontendRoot, "public");
const publicTarget = path.join(standaloneRoot, "public");
if (fs.existsSync(publicSource)) {
  fs.cpSync(publicSource, publicTarget, { recursive: true, force: true });
}

await import("../.next/standalone/server.js");

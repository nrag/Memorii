/**
 * Installed-client smoke (npm run test:installed).
 *
 * Packs the built SDK, installs it into a clean temporary project
 * OUTSIDE the source checkout, imports the public exports, and runs a
 * valid/denied protocol smoke against a one-shot loopback server.
 * Exits nonzero on any failure.
 */

import { execFileSync } from "node:child_process";
// execFileSync is used for npm pack/install; the smoke step must stay async.
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";

const here = path.dirname(fileURLToPath(import.meta.url));
const sdkRoot = path.join(here, "..");

// 1. Pack from the SDK root.
const tarball = execFileSync("npm", ["pack", "--silent"], {
  cwd: sdkRoot,
  encoding: "utf8",
}).trim();

// 2. Clean project outside the checkout.
const project = mkdtempSync(path.join(tmpdir(), "memorii-sdk-smoke-"));
writeFileSync(
  path.join(project, "package.json"),
  JSON.stringify(
    { name: "memorii-sdk-smoke", private: true, type: "module" },
    null,
    2,
  ),
);
execFileSync("npm", ["install", "--no-save", path.join(sdkRoot, tarball)], {
  cwd: project,
  stdio: "inherit",
});

// 3. One-shot loopback server for the protocol smoke.
const envelope = JSON.parse(
  readFileSync(path.join(sdkRoot, "test", "envelope.fixture.json"), "utf8"),
);
const server = createServer((request, response) => {
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    const authorized = request.headers["authorization"] === "Bearer smoke-credential";
    if (!authorized) {
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ code: "unauthenticated", retryable: false }));
      return;
    }
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(envelope));
  });
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;

// 4. Protocol smoke inside the installed project.
const smoke = `
import { RuntimeStateClient, RuntimeClientError } from "@memorii/runtime-client";
const ok = new RuntimeStateClient({ baseUrl: ${JSON.stringify(baseUrl)}, credential: "smoke-credential" });
const state = await ok.getState("task:smoke");
if (state.status !== "ready" || state.task_id !== "task:smoke") throw new Error("bad envelope");
const denied = new RuntimeStateClient({ baseUrl: ${JSON.stringify(baseUrl)}, credential: "forged" });
try {
  await denied.getState("task:smoke");
  throw new Error("expected unauthenticated");
} catch (error) {
  if (!(error instanceof RuntimeClientError) || error.code !== "unauthenticated") throw error;
}
console.log("installed smoke OK");
`;
writeFileSync(path.join(project, "smoke.mjs"), smoke);
// Async exec keeps THIS process's event loop alive so its loopback server
// can answer the child's fetches while the smoke runs.
const { execFile } = await import("node:child_process");
const { promisify } = await import("node:util");
try {
  await promisify(execFile)(process.execPath, ["smoke.mjs"], { cwd: project });
} finally {
  server.close();
}
console.log("test:installed passed");

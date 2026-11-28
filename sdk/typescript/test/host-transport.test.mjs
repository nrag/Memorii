import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const nativeRoot = new URL("../../../memorii/memorii/integrations/", import.meta.url);
const piTransport = new URL("pi/extension/internal/sidecar-transport.js", nativeRoot);
const openclawTransport = new URL("openclaw/plugin/internal/sidecar-transport.js", nativeRoot);
const driver = fileURLToPath(new URL("./fixtures/native-transport-driver.mjs", import.meta.url));
const execute = promisify(execFile);
const { createSidecarTransport } = await import(piTransport);

test("both host bundles use the same closed transport", async () => {
  assert.deepEqual(await readFile(piTransport), await readFile(openclawTransport));
  for (const invalid of [
    "http://example.test", "http://token@127.0.0.1", "http://localhost?token=secret",
    "http://127.1", "http://127.0.0.1\\@example.test", "https://127.0.0.1",
  ]) {
    assert.throws(() => createSidecarTransport(invalid, "/unused"), /loopback sidecar/);
  }
});

test("one native hook deadline spans chained requests and response body", async (context) => {
  const home = await privateHome(context);
  const seen = [];
  const server = await listen(context, (request, response) => {
    seen.push(request.url);
    if (request.url === "/first") {
      setTimeout(() => reply(response, { ready: true }), 1_400);
    } else {
      response.writeHead(200, { "content-type": "application/json" });
      response.write('{"pending":"unfinished');
    }
  });
  const transport = createSidecarTransport(server, join(home, "credential"));
  const started = performance.now();
  await assert.rejects(transport(async (request) => {
    await request("/first", {});
    await request("/second", {});
    await request("/unexpected", {});
  }));
  const elapsed = performance.now() - started;
  assert.ok(elapsed < 2_700, `observed ${elapsed} ms`);
  assert.deepEqual(seen, ["/first", "/second"]);
});

test("overlapping callbacks serialize for one adapter binding", async (context) => {
  const home = await privateHome(context);
  const seen = [];
  const server = await listen(context, (request, response) => {
    seen.push(request.url);
    reply(response, { ready: true });
  });
  const transport = createSidecarTransport(server, join(home, "credential"));
  await Promise.all([
    transport(async (request) => {
      await request("/first", {});
      await request("/second", {});
    }),
    transport(async (request) => { await request("/third", {}); }),
  ]);
  assert.deepEqual(seen, ["/first", "/second", "/third"]);
});

for (const host of ["pi", "openclaw"]) {
  test(`${host} reuses exact prepared proof after a process exits without an intake acknowledgement`, async (context) => {
    const home = await privateHome(context);
    const seen = [];
    let proof;
    const server = await listen(context, async (request, response) => {
      const body = await requestBody(request);
      const origin = request.headers["memorii-operation-origin"];
      seen.push({ route: request.url, body, origin, authorized: request.headers.authorization === "Bearer test-token" });
      switch (request.url) {
        case "/v1/runtime/state": reply(response, { task_version: 3 }); break;
        case "/v1/operations/prepare":
          proof = operationProof(body);
          reply(response, proof);
          break;
        case "/v1/runtime/intake":
          if (seen.filter(({ route }) => route === "/v1/runtime/intake").length === 1) {
            // Acceptance occurred but the actual client received no usable receipt.
            response.destroy();
          } else {
            reply(response, {
              operation_id: body.command.operation_id, producer_binding: proof.coordinate.client_namespace,
              request_digest: proof.coordinate.request_digest, state: "pending",
            });
          }
          break;
      }
    });
    const first = await drive(host, home, server, "resume");
    assert.equal(first.stdout.trim(), "resume-unavailable");
    const stateDir = join(home, ".memorii-adapter-state");
    const [journal] = await readdir(stateDir);
    assert.equal((await stat(join(stateDir, journal))).mode & 0o777, 0o600);
    const record = await readFile(join(stateDir, journal), "utf8");
    assert.ok(!record.includes("test-token"));
    assert.deepEqual(JSON.parse(record).proof, proof);

    const second = await drive(host, home, server, "resume");
    assert.equal(second.stdout.trim(), "resume-accepted");
    assert.deepEqual(seen.map(({ route }) => route), [
      "/v1/runtime/state", "/v1/operations/prepare", "/v1/runtime/intake", "/v1/runtime/intake",
    ]);
    assert.ok(seen.every(({ authorized }) => authorized));
    assert.deepEqual(seen.at(-1), seen.at(-2));
    assert.deepEqual(JSON.parse(seen.at(-1).origin), proof);
    assert.deepEqual(await readdir(stateDir), []);
  });

  test(`${host} retains original capture identity until committed acknowledgement`, async (context) => {
    const home = await privateHome(context);
    const captures = [];
    let proof;
    const server = await listen(context, async (request, response) => {
      const body = await requestBody(request);
      switch (request.url) {
        case "/v1/runtime/state": reply(response, { task_version: 3 }); break;
        case "/v1/operations/prepare": proof = operationProof(body); reply(response, proof); break;
        case "/v1/runtime/intake": reply(response, {
          operation_id: body.command.operation_id, producer_binding: proof.coordinate.client_namespace,
          request_digest: proof.coordinate.request_digest, state: "pending",
        }); break;
        case "/v1/runtime/source/recall": reply(response, { messages: [] }); break;
        case "/v1/runtime/source/capture":
          captures.push(body);
          reply(response, captures.length === 1
            ? { operation_id: "op:capture", status: "pending", detail: "PRIVATE_CAPTURE_MARKER" }
            : { operation_id: "op:capture", status: "committed", source_admission: { task_id: "task:test" } });
          break;
      }
    });
    const result = await drive(host, home, server, "capture");
    assert.match(result.stdout, /outcome unknown/);
    assert.ok(!result.stdout.includes("PRIVATE_CAPTURE_MARKER"));
    assert.equal(captures.length, 2);
    assert.deepEqual(captures[0], captures[1]);
    assert.deepEqual(captures[0].source, { kind: host, session_id: "session:test" });
    assert.equal(captures[0].delivery_id, host === "pi" ? "persisted-user" : "persisted:user");
    assert.equal(captures[0].text, "original native message");
  });
}

test("OpenClaw refuses a forwarded turn even after a matching native write", async (context) => {
  const home = await privateHome(context);
  const seen = [];
  let proof;
  const server = await listen(context, async (request, response) => {
    const body = await requestBody(request);
    seen.push(request.url);
    switch (request.url) {
      case "/v1/runtime/state": reply(response, { task_version: 3 }); break;
      case "/v1/operations/prepare": proof = operationProof(body); reply(response, proof); break;
      case "/v1/runtime/intake": reply(response, {
        operation_id: body.command.operation_id, producer_binding: proof.coordinate.client_namespace,
        request_digest: proof.coordinate.request_digest, state: "pending",
      }); break;
      case "/v1/runtime/source/recall": reply(response, { messages: [{ text: "synthetic private content" }] }); break;
      default: reply(response, { status: "denied" });
    }
  });
  const result = await drive("openclaw", home, server, "forwarded");
  assert.equal(result.stdout.trim(), "1");
  assert.deepEqual(seen, ["/v1/runtime/state", "/v1/operations/prepare", "/v1/runtime/intake"]);
});

async function privateHome(context) {
  const home = await mkdtemp(join(tmpdir(), "memorii-host-transport-"));
  await writeFile(join(home, "credential"), "test-token", { mode: 0o600 });
  context.after(() => rm(home, { recursive: true, force: true }));
  return home;
}

async function listen(context, callback) {
  const server = createServer(callback);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  context.after(() => new Promise((resolve) => {
    server.close(resolve);
    server.closeAllConnections();
  }));
  return `http://127.0.0.1:${server.address().port}`;
}

async function requestBody(request) {
  const chunks = [];
  for await (const bytes of request) chunks.push(bytes);
  return JSON.parse(Buffer.concat(chunks));
}

function reply(response, payload) {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

function operationProof(command) {
  return {
    coordinate: {
      installation_id: "installation", repository_id: "repository", generation_id: "generation",
      principal: "test", client_namespace: "namespace", operation_id: command.operation_id,
      request_digest: "a".repeat(64),
    },
    signature: "b".repeat(128),
  };
}

function drive(host, home, sidecar, action) {
  return execute(process.execPath, [driver, host, action], {
    env: {
      ...process.env,
      HOME: home,
      MEMORII_SIDECAR_URL: sidecar,
      MEMORII_CREDENTIAL_PATH: join(home, "credential"),
      MEMORII_TASK_ID: "task:test",
      MEMORII_PI_SESSION_ID: "session:test",
      MEMORII_OPENCLAW_SESSION_KEY: "session:test",
    },
    timeout: 5_000,
  });
}

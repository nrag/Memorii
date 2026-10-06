import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { RuntimeStateClient, RuntimeClientError } from "../dist/index.js";

test("loopback guard accepts loopback hosts and refuses everything else", () => {
  for (const baseUrl of [
    "http://127.0.0.1:8734",
    "http://localhost:8734",
    "http://[::1]:8734",
  ]) {
    assert.doesNotThrow(() => new RuntimeStateClient({ baseUrl, credential: "x" }));
  }
  for (const bad of [
    "http://0.0.0.0:8734",
    "http://127.0.0.1.evil.example",
    "http://127.0.0.1@evil.example",
    "https://127.0.0.1",
    "http://example.test",
  ]) {
    assert.throws(() => new RuntimeStateClient({ baseUrl: bad, credential: "x" }), /loopback/);
  }
});

test("unauthenticated error maps to the closed code", async () => {
  const client = new RuntimeStateClient({
    baseUrl: await serve(401, { code: "unauthenticated", retryable: false, detail: null }),
    credential: "wrong",
  });
  await assert.rejects(client.getState("task:one"), (error) => {
    assert.ok(error instanceof RuntimeClientError);
    assert.equal(error.code, "unauthenticated");
    assert.equal(error.httpStatus, 401);
    return true;
  });
});

test("stale cursor maps to its closed code and status", async () => {
  const client = new RuntimeStateClient({
    baseUrl: await serve(409, { code: "stale_cursor", retryable: false, detail: null }),
    credential: "right",
  });
  await assert.rejects(client.getState("task:one", { cursor: "abc.def" }), (error) => {
    assert.equal(error.code, "stale_cursor");
    assert.equal(error.httpStatus, 409);
    return true;
  });
});

test("non-object error body maps to unavailable without crashing", async () => {
  const client = new RuntimeStateClient({
    baseUrl: await serve(502, "bad gateway", "text/plain"),
    credential: "right",
  });
  await assert.rejects(client.getState("task:one"), (error) => {
    assert.equal(error.code, "unavailable");
    return true;
  });
});

test("authorized state parses into the envelope shape", async () => {
  const envelope = {
    protocol_version: 1,
    task_id: "task:one",
    revision: 4,
    status: "reconcile_required",
    goal: "Diagnose latency",
    ready_work: [],
    blocked_work: [],
    constraints: [],
    remaining_acceptance: [],
    candidate_hypotheses: [],
    committed_hypotheses: [],
    frontier: [],
    unresolved_questions: [],
    unexplained_evidence: [],
    reopenable_branches: [],
    recommendation_kind: "reconcile",
    recommendation_target: "action:pending",
    recommendation_evidence: [],
    pending_actions: ["action:pending"],
    source_refs: [],
    omissions: ["frontier truncated at 16 items; page for more"],
    state_digest: "a".repeat(64),
  };
  const client = new RuntimeStateClient({
    baseUrl: await serve(200, envelope),
    credential: "right",
  });
  const state = await client.getState("task:one");
  assert.equal(state.status, "reconcile_required");
  assert.equal(state.recommendation_kind, "reconcile");
  assert.deepEqual(state.pending_actions, ["action:pending"]);
});

test("submitEvent posts the closed command and parses the intake record", async () => {
  const seen = [];
  const server = createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      seen.push({ url: request.url, auth: request.headers.authorization, body: JSON.parse(Buffer.concat(chunks).toString()) });
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({
        operation_id: "op:1",
        producer_binding: "host:principal:a",
        request_digest: "a".repeat(64),
        state: "pending",
      }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  server.unref();
  const client = new RuntimeStateClient({
    baseUrl: `http://127.0.0.1:${server.address().port}`,
    credential: "credential:one",
  });
  const record = await client.submitEvent(
    { kind: "record_observation", operation_id: "op:1", task_id: "task:one", expected_revision: 0 },
    { transportMessageId: "msg:7" },
  );
  assert.equal(record.operation_id, "op:1");
  assert.equal(record.state, "pending");
  assert.equal(seen[0].url, "/v1/runtime/intake");
  assert.equal(seen[0].auth, "Bearer credential:one");
  assert.equal(seen[0].body.protocol_version, 1);
  assert.equal(seen[0].body.command.kind, "record_observation");
  assert.equal(seen[0].body.transport_message_id, "msg:7");
});

test("submitEvent maps conflict to its closed code", async () => {
  const client = new RuntimeStateClient({
    baseUrl: await serve(409, { code: "conflict", retryable: false, detail: null }),
    credential: "right",
  });
  await assert.rejects(
    client.submitEvent({ kind: "checkpoint_task", operation_id: "op:2", task_id: "task:one", expected_revision: 3 }),
    (error) => {
      assert.equal(error.code, "conflict");
      assert.equal(error.httpStatus, 409);
      return true;
    },
  );
});

/** Minimal one-shot HTTP server serving a fixed response; loopback only. */
async function serve(status, body, contentType = "application/json") {
  const server = createServer((request, response) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => {
      response.writeHead(status, { "content-type": contentType });
      response.end(typeof body === "string" ? body : JSON.stringify(body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  server.unref();
  return `http://127.0.0.1:${server.address().port}`;
}

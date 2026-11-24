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

test("managed intake transports the original prepared operation proof", async () => {
  const command = { kind: "start_task", operation_id: "op:managed", goal: "Start" };
  const proof = {
    coordinate: {
      installation_id: "installation", repository_id: "repository", generation_id: "generation",
      principal: "host\u2603", client_namespace: "namespace", operation_id: command.operation_id,
      request_digest: "a".repeat(64),
    },
    signature: "b".repeat(128),
  };
  const requests = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({ path: request.url, headers: request.headers, body: JSON.parse(Buffer.concat(chunks)) });
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(request.url === "/v1/operations/prepare" ? proof : {
      operation_id: command.operation_id, producer_binding: "namespace",
      request_digest: proof.coordinate.request_digest, state: "pending",
    }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const client = new RuntimeStateClient({ baseUrl: `http://127.0.0.1:${server.address().port}`, credential: "right" });
    const prepared = await client.prepareOperation(command);
    assert.deepEqual(prepared, proof);
    assert.equal((await client.submitOperation(command, prepared)).state, "pending");
    assert.equal(requests[0].path, "/v1/operations/prepare");
    assert.deepEqual(requests[0].body, command);
    assert.equal(requests[1].path, "/v1/runtime/intake");
    assert.deepEqual(requests[1].body.command, command);
    assert.deepEqual(JSON.parse(requests[1].headers["memorii-operation-origin"]), proof);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("readConsolidation sends the origin and paging selectors to the authenticated route", async () => {
  const selectors = {
    protocol_version: 1, task_id: "task:one", origin_operation_id: "op:pause", cursor: "cursor:one", page_size: 2,
  };
  const page = {
    protocol_version: 1, result_id: "a".repeat(64), origin_revision: 5, outputs: [], omissions: [],
    continuation_cursor: null,
  };
  const requests = [];
  const server = createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({
      path: request.url, method: request.method, authorization: request.headers.authorization,
      body: JSON.parse(Buffer.concat(chunks)),
    });
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(page));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const client = new RuntimeStateClient({ baseUrl: `http://127.0.0.1:${server.address().port}`, credential: "right" });
    assert.deepEqual(await client.readConsolidation(selectors), page);
    assert.deepEqual(requests, [{
      path: "/v1/consolidation/read", method: "POST", authorization: "Bearer right", body: selectors,
    }]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("writeback decision submits the original prepared proof with the exact selectors", async () => {
  const request = {
    host_binding: { installation_id: "installation", client_namespace: "namespace", task_id: "task:one" },
    task_id: "task:one", result_id: "a".repeat(64), output_id: "b".repeat(64),
    expected_offer_version: 1, expected_payload_digest: "c".repeat(64), operation_id: "op:writeback",
    decision: "accept",
  };
  const proof = {
    coordinate: {
      installation_id: "installation", repository_id: "repository", generation_id: "generation",
      principal: "user\u2603", client_namespace: "namespace", operation_id: request.operation_id,
      request_digest: "d".repeat(64),
    },
    signature: "e".repeat(128),
  };
  const receipt = {
    decision_id: "f".repeat(64), outcome: "accepted", offer_version: 2,
    delivery_id: "1".repeat(64), delivery_status: "pending",
  };
  const seen = [];
  const server = createServer(async (incoming, response) => {
    const chunks = [];
    for await (const chunk of incoming) chunks.push(chunk);
    seen.push({
      path: incoming.url, body: JSON.parse(Buffer.concat(chunks)),
      header: incoming.headers["memorii-operation-origin"],
    });
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(incoming.url === "/v1/operations/prepare" ? proof : receipt));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const client = new RuntimeStateClient({ baseUrl: `http://127.0.0.1:${server.address().port}`, credential: "right" });
    const prepared = await client.prepareOperation(request);
    assert.deepEqual(await client.decideWriteback(request, prepared), receipt);
    assert.equal(seen[0].path, "/v1/operations/prepare");
    assert.deepEqual(seen[0].body, request);
    assert.equal(seen[1].path, "/v1/consolidation/decision");
    assert.deepEqual(seen[1].body, request);
    assert.deepEqual(JSON.parse(seen[1].header), proof);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
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

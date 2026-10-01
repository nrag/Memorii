/**
 * Memorii runtime-state extension for the Pi coding agent.
 *
 * Host contract: pi-coding-agent-extension/v1, bound to the authoritative
 * 0.99.x event surface. Session starts are reason-aware (new sessions start
 * the authorized task; resumes continue it). User messages are captured as
 * authentic source evidence through the durable intake route; tool events
 * record dispatches and results with honest compare-and-swap revisions read
 * from the state route. Forks are denied unless the owner granted explicit
 * branch authorization (MEMORII_AUTHORIZE_BRANCH=1) — the pinned contract's
 * rule that a session branch never continues an authorized task implicitly.
 * The credential is read from an owner-only file; sidecar failures surface
 * as extension errors, never silently skipped events.
 */

import { readFileSync } from "node:fs";

const HOST_CONTRACT = "pi-coding-agent-extension/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/pi-extension.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:pi-session";
/** Monotonic per-process operation counter; idempotence is keyed by
 * (operation id, request digest), so retries reuse the same id. */
let operationCounter = 0;

function bearerToken(): string {
  const raw = readFileSync(CREDENTIAL_PATH, "utf8").trim();
  if (!raw) {
    throw new Error("memorii sidecar credential is empty");
  }
  return raw;
}

async function taskExists(): Promise<boolean> {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/state`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, task_id: TASK_ID, view: "summary" }),
  });
  if (response.status === 404) {
    return false;
  }
  if (!response.ok) {
    throw new Error(`memorii state read failed: ${response.status}`);
  }
  await response.json();
  return true;
}

async function currentRevision(): Promise<number> {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/state`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, task_id: TASK_ID, view: "summary" }),
  });
  if (response.status === 404 || response.status === 409) {
    // The task's start command is still pending in the spool; observations
    // are not revision-gated, so a provisional 0 keeps the turn flowing.
    return 0;
  }
  if (!response.ok) {
    throw new Error(`memorii state read failed: ${response.status}`);
  }
  const envelope = (await response.json()) as { revision?: number };
  return typeof envelope.revision === "number" ? envelope.revision : 0;
}

async function submitCommand(command: Record<string, unknown>): Promise<void> {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/intake`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, command }),
  });
  if (!response.ok) {
    throw new Error(
      `memorii intake rejected ${command["kind"]}: ${response.status}`,
    );
  }
  await response.json();
}

function nextOperationId(prefix: string): string {
  operationCounter += 1;
  return `pi:${prefix}:${process.pid}:${operationCounter}`;
}

interface PiSessionStartEvent {
  reason?: "startup" | "reload" | "new" | "resume" | "fork";
}

interface PiMessageEvent {
  message?: { role?: string };
}

export default function memoriiExtension(pi: unknown): void {
  const host = pi as {
    on?: (
      event: string,
      handler: (event: never) => unknown,
    ) => () => void;
  };
  if (typeof host?.on !== "function") {
    throw new Error(`unsupported Pi host surface for ${HOST_CONTRACT}`);
  }

  host.on("session_start", async (_event: PiSessionStartEvent) => {
    // Hosts continue operator-provisioned tasks; they never mint their own
    // (start_task generates a server-side task id by contract). A session
    // without its provisioned task fails closed instead of fabricating one.
    if (!(await taskExists())) {
      throw new Error(`no provisioned task ${TASK_ID} for this host session`);
    }
    const revision = await currentRevision();
    await submitCommand({
      kind: "resume_task",
      operation_id: nextOperationId("resume"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
  });

  host.on(
    "session_before_fork",
    (): { cancel: boolean } | undefined =>
      process.env.MEMORII_AUTHORIZE_BRANCH === "1"
        ? undefined
        : { cancel: true },
  );

  host.on("message_start", async (event: PiMessageEvent) => {
    if (event?.message?.role !== "user") {
      return; // only user messages are authentic source evidence
    }
    const revision = await currentRevision();
    await submitCommand({
      kind: "record_observation",
      operation_id: nextOperationId("observe"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
  });

  host.on("tool_call", async () => {
    const revision = await currentRevision();
    await submitCommand({
      kind: "record_action_dispatch",
      operation_id: nextOperationId("dispatch"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
  });

  host.on("tool_result", async () => {
    const revision = await currentRevision();
    await submitCommand({
      kind: "record_action_result",
      operation_id: nextOperationId("result"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
  });
}

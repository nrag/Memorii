/**
 * Memorii runtime-state extension for the Pi coding agent.
 *
 * Host contract: pi-coding-agent-extension/v1. The extension translates Pi
 * session events into closed runtime commands and submits them through the
 * Memorii sidecar's durable intake route (POST /v1/runtime/intake) with the
 * installation-issued bearer credential read from an owner-only file. The
 * current task revision is read from the state route before each command so
 * compare-and-swap expectations stay honest. It never decides memory
 * semantics locally, never puts the credential in argv or logs, and surfaces
 * sidecar failures as extension errors instead of silently skipping events.
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

async function currentRevision(): Promise<number> {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/state`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, task_id: TASK_ID, view: "summary" }),
  });
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

export default function memoriiExtension(pi: unknown): void {
  const host = pi as {
    on?: (event: string, handler: (event: unknown) => unknown) => void;
  };
  if (typeof host?.on !== "function") {
    throw new Error(`unsupported Pi host surface for ${HOST_CONTRACT}`);
  }

  host.on("session_start", async () => {
    await submitCommand({
      kind: "start_task",
      operation_id: nextOperationId("start"),
      goal: `Pi session ${process.env.PI_SESSION_ID ?? "unknown"}`,
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

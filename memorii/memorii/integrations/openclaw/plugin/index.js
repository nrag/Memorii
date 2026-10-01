/**
 * Memorii memory plugin for OpenClaw.
 *
 * Host contract: openclaw-memory-plugin/v1 (major pinned; the plugin fails
 * closed when the host surface does not match). Only user messages become
 * source evidence — system events and forwarded inputs are classified and
 * never submitted as observations. Channel account/sender identity travels
 * in the command flow, never as authority: the bearer credential decides
 * the producer binding server-side. Session switches resume the same
 * authorized task; the credential is read from an owner-only file and never
 * appears in argv or logs.
 */

import { readFileSync } from "node:fs";

export const HOST_CONTRACT = "openclaw-memory-plugin/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/openclaw-plugin.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:openclaw-session";
let operationCounter = 0;

function bearerToken() {
  const raw = readFileSync(CREDENTIAL_PATH, "utf8").trim();
  if (!raw) {
    throw new Error("memorii sidecar credential is empty");
  }
  return raw;
}

async function currentRevision() {
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
  const envelope = await response.json();
  return typeof envelope.revision === "number" ? envelope.revision : 0;
}

async function submitCommand(command) {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/intake`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, command }),
  });
  if (!response.ok) {
    throw new Error(`memorii intake rejected ${command.kind}: ${response.status}`);
  }
  await response.json();
}

function nextOperationId(prefix) {
  operationCounter += 1;
  return `openclaw:${prefix}:${process.pid}:${operationCounter}`;
}

/** Classify one host input per the pinned contract; forwarded and system
 * inputs are never eligible as source evidence. */
export function classifyInput(input) {
  const kind = input?.input_kind;
  const sender = input?.sender;
  if (!kind || !sender?.channel_id || !sender?.account_id || !sender?.sender_id) {
    throw new Error("input does not carry the pinned sender identity");
  }
  return { eligible: kind === "user_message", kind, sender };
}

export function register(host) {
  if (typeof host?.on !== "function" || typeof host?.memorySlot !== "function") {
    throw new Error(`unsupported OpenClaw host surface for ${HOST_CONTRACT}`);
  }

  host.on("session_start", async () => {
    await submitCommand({
      kind: "start_task",
      operation_id: nextOperationId("start"),
      goal: "OpenClaw channel session",
    });
  });

  host.on("session_switch", async () => {
    const revision = await currentRevision();
    await submitCommand({
      kind: "resume_task",
      operation_id: nextOperationId("resume"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
  });

  host.on("prompt_inject", async (input) => {
    const classification = classifyInput(input);
    if (!classification.eligible) {
      return null; // forwarded/system inputs never become source evidence
    }
    const revision = await currentRevision();
    await submitCommand({
      kind: "record_observation",
      operation_id: nextOperationId("observe"),
      task_id: TASK_ID,
      expected_revision: revision,
    });
    return null;
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
}

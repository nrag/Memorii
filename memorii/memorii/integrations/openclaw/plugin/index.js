/**
 * Memorii memory plugin for OpenClaw (native plugin shape).
 *
 * Host contract: openclaw-memory-plugin/v1 (major pinned; the plugin fails
 * closed when the host surface does not match). Only user messages become
 * source evidence — forwarded and system inputs are classified out. Channel
 * account/sender identity travels in the event flow, never as authority:
 * the bearer credential decides the producer binding server-side. Hosts
 * never mint tasks: the session hook resumes the operator-provisioned task
 * or fails closed. The credential is read from an owner-only file and never
 * appears in argv or logs.
 */

import { readFileSync } from "node:fs";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

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

async function readState() {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/state`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({ protocol_version: 1, task_id: TASK_ID, view: "summary" }),
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`memorii state read failed: ${response.status}`);
  }
  const envelope = await response.json();
  return typeof envelope.revision === "number" ? envelope.revision : 0;
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
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

let resumedThisProcess = false;

async function onSessionStart() {
  if (resumedThisProcess) {
    return undefined;
  }
  resumedThisProcess = true;
  const revision = await readState();
  if (revision === null) {
    throw new Error(`no provisioned task ${TASK_ID} for this host session`);
  }
  await submitCommand({
    kind: "resume_task",
    operation_id: nextOperationId("resume"),
    task_id: TASK_ID,
    expected_revision: revision,
  });
  return undefined;
}

async function onTranscriptWrite(context) {
  // before_message_write is the single authoritative transcript seam: it
  // fires once per message persisted to the session with
  // {message: {role, content}}. Only user messages are authentic source
  // evidence; assistant writes are derived, never source. The first user
  // write of a process resumes the provisioned task — gateway turns do not
  // dispatch session_start to plugins, so session adoption lands here.
  if (context?.message?.role !== "user") {
    return undefined;
  }
  if (!resumedThisProcess) {
    await onSessionStart();
  }
  const text = typeof context?.message?.content === "string" ? context.message.content : "";
  const revision = (await readState()) ?? 0;
  await submitCommand({
    kind: "record_observation",
    operation_id: nextOperationId("observe"),
    task_id: TASK_ID,
    expected_revision: revision,
    source_digest: await sha256Hex(text),
  });
  return undefined;
}

async function onBeforeToolCall() {
  const revision = (await readState()) ?? 0;
  await submitCommand({
    kind: "record_action_dispatch",
    operation_id: nextOperationId("dispatch"),
    task_id: TASK_ID,
    expected_revision: revision,
  });
  return undefined;
}

async function onAfterToolCall() {
  const revision = (await readState()) ?? 0;
  await submitCommand({
    kind: "record_action_result",
    operation_id: nextOperationId("result"),
    task_id: TASK_ID,
    expected_revision: revision,
  });
  return undefined;
}

export default definePluginEntry({
  id: "memorii",
  name: "Memorii",
  description: "Memorii durable runtime state for OpenClaw sessions.",
  version: "1.0.0",
  register(api) {
    if (typeof api?.on !== "function") {
      throw new Error(`unsupported OpenClaw host surface for ${HOST_CONTRACT}`);
    }
    // The typed hook runner dispatches these events; api.on is the
    // supported registration surface for them.
    api.on("session_start", onSessionStart);
    api.on("before_message_write", onTranscriptWrite);
    api.on("before_tool_call", onBeforeToolCall);
    api.on("after_tool_call", onAfterToolCall);
  },
});

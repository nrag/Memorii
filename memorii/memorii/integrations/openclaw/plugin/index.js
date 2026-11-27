/**
 * Memorii memory plugin for OpenClaw (native plugin shape).
 *
 * Host contract: openclaw-memory-plugin/v1 (major pinned; the plugin fails
 * closed when the host surface does not match). Only user messages are
 * candidates for source evidence. The bearer credential decides the
 * producer binding server-side and the source owner must approve any
 * observation before intake. Hosts
 * never mint tasks: the explicitly bound MEMORII_OPENCLAW_SESSION_KEY
 * resumes an operator-provisioned task. The credential lives in an
 * owner-only file.
 */

import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export const HOST_CONTRACT = "openclaw-memory-plugin/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/openclaw-plugin.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:openclaw-session";
const SESSION_KEY = process.env.MEMORII_OPENCLAW_SESSION_KEY;

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
    redirect: "error",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
    },
    body: JSON.stringify({
      protocol_version: 1, task_id: TASK_ID, view: "summary", include_task_version: true,
    }),
  });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`memorii state read failed: ${response.status}`);
  }
  const envelope = await response.json();
  if (!Number.isSafeInteger(envelope.task_version) || envelope.task_version < 1) {
    throw new Error("memorii state omitted the task version");
  }
  return envelope.task_version;
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function prepareCommand(command) {
  const headers = {
    "content-type": "application/json",
    authorization: `Bearer ${bearerToken()}`,
  };
  const prepared = await fetch(`${SIDECAR_URL}/v1/operations/prepare`, {
    method: "POST",
    redirect: "error",
    headers,
    body: JSON.stringify(command),
  });
  if (!prepared.ok) {
    throw new Error(`memorii prepare rejected ${command.kind}: ${prepared.status}`);
  }
  const proof = (await prepared.text()).replace(
    /[^\x00-\x7f]/g,
    (unit) => `\\u${unit.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
  return { command, proof };
}

async function submitCommand({ command, proof }) {
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/intake`, {
    method: "POST",
    redirect: "error",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${bearerToken()}`,
      "Memorii-Operation-Origin": proof,
    },
    body: JSON.stringify({ protocol_version: 1, command }),
  });
  if (!response.ok) {
    throw new Error(`memorii intake rejected ${command.kind}: ${response.status}`);
  }
  await response.json();
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

let pendingResume;
let preparedResume;

async function resumeTask() {
  if (!preparedResume) {
    const revision = await readState();
    if (revision === null) {
      throw new Error(`no provisioned task ${TASK_ID} for this host session`);
    }
    preparedResume = await prepareCommand({
      kind: "resume_task",
      operation_id: `openclaw:resume:${randomUUID()}`,
      task_id: TASK_ID,
      expected_revision: revision,
    });
  }
  // The sidecar may admit the operation before its HTTP response is lost.
  await submitCommand(preparedResume);
}

async function resumeBoundSession(_event, context) {
  if (context?.sessionKey !== SESSION_KEY) return;
  pendingResume ??= resumeTask().catch((error) => {
    pendingResume = undefined;
    throw error;
  });
  await pendingResume;
}

function onTranscriptWrite(event, context) {
  // before_message_write is the single authoritative transcript seam: it
  // fires once per message persisted to the session with
  // {message: {role, content}}. The pinned hook is synchronous.
  if (context?.sessionKey !== SESSION_KEY || event?.message?.role !== "user") return;
  const text = event.message.content;
  if (typeof text !== "string" || !text.trim()) return;
  void prepareObservation(text, context).catch((error) => {
    console.error("memorii observation failed", error.message);
  });
}

async function prepareObservation(text, context) {
  // A continuation can write to the transcript without running prompt hooks.
  await resumeBoundSession(undefined, context);
  const revision = await readState();
  if (revision === null) throw new Error("memorii observation task is unavailable");
  await submitCommand(await prepareCommand({
    kind: "record_observation",
    operation_id: `openclaw:observe:${randomUUID()}`,
    task_id: TASK_ID,
    expected_revision: revision,
    source_digest: await sha256Hex(text),
  }));
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
    if (!SESSION_KEY) {
      throw new Error("memorii requires an operator-selected MEMORII_OPENCLAW_SESSION_KEY");
    }
    api.on("session_start", resumeBoundSession);
    // When the gateway builds a prompt, await the resume intake receipt.
    api.on("before_prompt_build", resumeBoundSession);
    api.on("before_message_write", onTranscriptWrite);
  },
});

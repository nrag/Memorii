/**
 * Memorii runtime-state extension for the Pi coding agent.
 *
 * Host contract: pi-coding-agent-extension/v1, bound to the authoritative
 * 0.99.x event surface. Session starts resume the provisioned task through
 * signed intake only for the operator-selected MEMORII_PI_SESSION_ID. The
 * managed source owner must approve any observation
 * before intake. Interactive forks require MEMORII_AUTHORIZE_BRANCH=1.
 * A branch must match the operator-selected session before using Memorii.
 * The credential is read from an owner-only file; sidecar failures surface
 * as extension errors, never silently skipped events.
 */

import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";

const HOST_CONTRACT = "pi-coding-agent-extension/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/pi-extension.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:pi-session";
const SESSION_ID = process.env.MEMORII_PI_SESSION_ID;

function bearerToken(): string {
  const raw = readFileSync(CREDENTIAL_PATH, "utf8").trim();
  if (!raw) {
    throw new Error("memorii sidecar credential is empty");
  }
  return raw;
}

async function currentTaskVersion(): Promise<number> {
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
  if (!response.ok) {
    throw new Error(`memorii state read failed: ${response.status}`);
  }
  const envelope = (await response.json()) as { task_version?: number };
  const version = envelope.task_version;
  if (typeof version !== "number" || !Number.isSafeInteger(version) || version < 1) {
    throw new Error("memorii state omitted the task version");
  }
  return version;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function submitCommand(command: Record<string, unknown>): Promise<void> {
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
    throw new Error(`memorii prepare rejected ${command["kind"]}: ${prepared.status}`);
  }
  const proof = (await prepared.text()).replace(
    /[^\x00-\x7f]/g,
    (unit) => `\\u${unit.charCodeAt(0).toString(16).padStart(4, "0")}`,
  );
  const response = await fetch(`${SIDECAR_URL}/v1/runtime/intake`, {
    method: "POST",
    redirect: "error",
    headers: {
      ...headers,
      "Memorii-Operation-Origin": proof,
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

interface PiSessionStartEvent {
  reason?: "startup" | "reload" | "new" | "resume" | "fork";
}

interface PiMessageEvent {
  message?: { role?: string; content?: string | { type: string; text?: string }[] };
}

interface PiSessionContext {
  sessionManager: { getSessionId(): string };
}

function requireBoundSession(context: PiSessionContext): void {
  if (!SESSION_ID) {
    throw new Error("memorii requires an operator-selected MEMORII_PI_SESSION_ID");
  }
  if (context.sessionManager.getSessionId() !== SESSION_ID) {
    throw new Error("memorii denied an unbound Pi session");
  }
}

export function userMessageText(event: PiMessageEvent): string | undefined {
  if (event.message?.role !== "user") return undefined;
  const content = event.message.content;
  const text = typeof content === "string" ? content : Array.isArray(content)
    ? content.flatMap((block) =>
      block?.type === "text" && typeof block.text === "string" ? [block.text] : [],
    ).join("\n")
    : undefined;
  return text?.trim() ? text : undefined;
}

export default function memoriiExtension(pi: unknown): void {
  const host = pi as {
    on?: (
      event: string,
      handler: (event: never, context: PiSessionContext) => unknown,
    ) => () => void;
  };
  if (typeof host?.on !== "function") {
    throw new Error(`unsupported Pi host surface for ${HOST_CONTRACT}`);
  }

  host.on("session_start", async (_event: PiSessionStartEvent, context: PiSessionContext) => {
    // Hosts continue operator-provisioned tasks; they never mint their own
    // (start_task generates a server-side task id by contract). A session
    // without its provisioned task fails closed instead of fabricating one.
    requireBoundSession(context);
    const revision = await currentTaskVersion();
    await submitCommand({
      kind: "resume_task",
      operation_id: `pi:resume:${randomUUID()}`,
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

  host.on("message_start", async (event: PiMessageEvent, context: PiSessionContext) => {
    const text = userMessageText(event);
    if (text === undefined) return;
    requireBoundSession(context);
    const revision = await currentTaskVersion();
    await submitCommand({
      kind: "record_observation",
      operation_id: `pi:observe:${randomUUID()}`,
      task_id: TASK_ID,
      expected_revision: revision,
      source_digest: await sha256Hex(text),
    });
  });
}

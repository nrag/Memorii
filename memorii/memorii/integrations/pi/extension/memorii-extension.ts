/**
 * Memorii runtime-state extension for the Pi coding agent.
 *
 * Host contract: pi-coding-agent-extension/v1, bound to the authoritative
 * 0.99.x event surface. Session starts resume the provisioned task through
 * signed intake only for the operator-selected MEMORII_PI_SESSION_ID. Raw
 * user text uses the managed source capture and recall routes. Interactive
 * forks require MEMORII_AUTHORIZE_BRANCH=1.
 * A branch must match the operator-selected session before using Memorii.
 * The credential is read from an owner-only file; sidecar failures surface
 * as extension errors, never silently skipped events.
 */

import { debuglog } from "node:util";
import {
  capturedObservation,
  createSidecarTransport,
  recalledUserData,
  resumeTask,
  type SidecarRequest,
} from "./internal/sidecar-transport.js";

const HOST_CONTRACT = "pi-coding-agent-extension/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/pi-extension.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:pi-session";
const SESSION_ID = process.env.MEMORII_PI_SESSION_ID;
const MAX_PENDING_MESSAGES = 16;
const log = debuglog("memorii");

interface PiSessionStartEvent {
  reason?: "startup" | "reload" | "new" | "resume" | "fork";
}

interface PiMessageEvent {
  message?: PiMessage;
}

interface PiMessage {
  role?: string;
  content?: string | { type: string; text?: string }[];
  timestamp?: number;
}

interface PiSessionContext {
  hasUI: boolean;
  ui: { notify(message: string, type: "warning"): void };
  sessionManager: {
    getSessionId(): string;
    getBranch(): { type: string; id: string; message?: PiMessage }[];
  };
}

function warn(context: PiSessionContext, message: string): void {
  log("%s", message);
  if (context.hasUI) context.ui.notify(message, "warning");
}

function requireBoundSession(context: PiSessionContext): string {
  if (!SESSION_ID) {
    throw new Error("memorii requires an operator-selected MEMORII_PI_SESSION_ID");
  }
  if (context.sessionManager.getSessionId() !== SESSION_ID) {
    throw new Error("memorii denied an unbound Pi session");
  }
  return SESSION_ID;
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
  const withSidecar = createSidecarTransport(SIDECAR_URL, CREDENTIAL_PATH);
  const pendingUsers = new Set<PiMessage>();
  let resumedBinding: string | undefined;

  async function ensureResumed(request: SidecarRequest, binding: string, sessionId: string): Promise<void> {
    if (resumedBinding === binding) return;
    await resumeTask(request, binding, { kind: "pi", taskId: TASK_ID, sessionId });
    resumedBinding = binding;
  }

  host.on("session_start", async (_event: PiSessionStartEvent, context: PiSessionContext) => {
    const sessionId = requireBoundSession(context);
    try {
      await withSidecar((request, binding) => ensureResumed(request, binding, sessionId));
    } catch {
      // Node can include response bytes and credential paths in its errors.
      throw new Error("Memorii session resume unavailable");
    }
  });

  host.on(
    "session_before_fork",
    (): { cancel: boolean } | undefined =>
      process.env.MEMORII_AUTHORIZE_BRANCH === "1"
        ? undefined
        : { cancel: true },
  );

  host.on("message_end", (event: PiMessageEvent, context: PiSessionContext) => {
    if (!event.message || userMessageText(event) === undefined) return;
    requireBoundSession(context);
    if (pendingUsers.size >= MAX_PENDING_MESSAGES && !pendingUsers.has(event.message)) {
      warn(context, "Memorii capture outcome unknown (local pending limit)");
      return;
    }
    pendingUsers.add(event.message);
  });

  host.on("agent_end", async (_event, context: PiSessionContext) => {
    if (!pendingUsers.size) return;
    const sessionId = requireBoundSession(context);
    try {
      await withSidecar(async (request, binding) => {
        await ensureResumed(request, binding, sessionId);
        // Pi persists a message after message_end and before agent_end.
        // Retry only an original message from the same persisted branch.
        const branch = context.sessionManager.getBranch();
        for (const message of pendingUsers) {
          const text = userMessageText({ message });
          const entries = branch.filter((entry) => entry.type === "message" && entry.message === message);
          const entry = entries.length === 1 ? entries[0] : undefined;
          if (text === undefined || !entry?.id) {
            warn(context, "Memorii source capture requires a unique native Pi message entry");
            continue;
          }
          const receipt = await request("/v1/runtime/source/capture", {
            task_id: TASK_ID, source: { kind: "pi", session_id: sessionId }, delivery_id: entry.id, text,
          });
          if (!capturedObservation(receipt, TASK_ID)) throw new Error("Memorii capture receipt unavailable");
          pendingUsers.delete(message);
        }
      });
    } catch {
      warn(context, "Memorii source capture outcome unknown");
    }
  });

  host.on("context", async (event: { messages: PiMessage[] }, context: PiSessionContext) => {
    const sessionId = requireBoundSession(context);
    try {
      return await withSidecar(async (request, binding) => {
        await ensureResumed(request, binding, sessionId);
        const envelope = await request("/v1/runtime/source/recall", {
          task_id: TASK_ID, source: { kind: "pi", session_id: sessionId },
        });
        const text = recalledUserData(envelope);
        if (text === undefined) return undefined;
        const history = { role: "user", content: [{ type: "text", text }], timestamp: Date.now() };
        return { messages: [history, ...event.messages] };
      });
    } catch {
      warn(context, "Memorii source recall unavailable");
      return undefined;
    }
  });
}

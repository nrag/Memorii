/**
 * Memorii memory plugin for OpenClaw (native plugin shape).
 *
 * Host contract: openclaw-memory-plugin/v1 (host pinned; the plugin fails
 * closed when the host surface does not match). Only user messages are
 * candidates for source evidence. The managed source routes authorize
 * capture and recall for the dedicated local gateway session. Hosts
 * never mint tasks: the explicitly bound MEMORII_OPENCLAW_SESSION_KEY
 * resumes an operator-provisioned task. The credential lives in an
 * owner-only file.
 */

import { buildMemorySystemPromptAddition, delegateCompactionToRuntime } from "openclaw/plugin-sdk/core";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import {
  capturedObservation,
  createSidecarTransport,
  recalledUserData,
  resumeTask,
} from "./internal/sidecar-transport.js";

export const HOST_CONTRACT = "openclaw-memory-plugin/v1";
const SIDECAR_URL = process.env.MEMORII_SIDECAR_URL ?? "http://127.0.0.1:8762";
const CREDENTIAL_PATH =
  process.env.MEMORII_CREDENTIAL_PATH ?? "/run/memorii/openclaw-plugin.credential";
const TASK_ID = process.env.MEMORII_TASK_ID ?? "task:openclaw-session";
const SESSION_KEY = process.env.MEMORII_OPENCLAW_SESSION_KEY;
const MAX_PENDING_MESSAGES = 16;

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

export default definePluginEntry({
  id: "memorii",
  name: "Memorii",
  description: "Memorii durable runtime state for OpenClaw sessions.",
  version: "1.0.0",
  register(api) {
    if (typeof api?.on !== "function" || typeof api?.registerContextEngine !== "function") {
      throw new Error(`unsupported OpenClaw host surface for ${HOST_CONTRACT}`);
    }
    if (!SESSION_KEY) {
      throw new Error("memorii requires an operator-selected MEMORII_OPENCLAW_SESSION_KEY");
    }
    const withSidecar = createSidecarTransport(SIDECAR_URL, CREDENTIAL_PATH);
    const pendingMessages = new Map();
    const source = { kind: "openclaw", session_id: SESSION_KEY };
    let resumedBinding;
    let recallTurn;

    async function ensureResumed(request, binding) {
      if (binding === resumedBinding) return;
      await resumeTask(request, binding, { kind: "openclaw", taskId: TASK_ID, sessionId: SESSION_KEY });
      resumedBinding = binding;
    }

    function localDeliveryId(context) {
      if (context?.sessionKey !== SESSION_KEY || context.trigger !== "user"
          || context.channel || context.messageProvider || context.inputProvenance) return undefined;
      if (typeof context.runId !== "string" || !context.runId) return undefined;
      return `${context.runId}:user`;
    }

    // The embedded host serializes each session's turns. Only assemble() uses
    // the reserved admission, and it consumes it before requesting recall.
    api.on("before_model_resolve", (event, context) => {
      if (context?.sessionKey !== SESSION_KEY) return;
      recallTurn = undefined;
      const deliveryId = localDeliveryId(context);
      if (!deliveryId || typeof context.sessionId !== "string" || !context.sessionId) return;
      const admission = pendingMessages.get(deliveryId);
      if (admission && event?.prompt === admission.text) {
        recallTurn = { deliveryId, sessionId: context.sessionId, admission };
      }
    });

    api.registerContextEngine("memorii", () => ({
      info: {
        id: "memorii",
        name: "Memorii",
        ownsCompaction: false,
        transcriptSemantics: {
          currentTurnFence: "before-current-turn-entry-v1",
          turnAdvancementIdempotency: "atomic-idempotent-v1",
        },
      },
      // The host owns the transcript. There is no context-engine store to advance.
      async commitTurn() { return { status: "committed" }; },
      async ingest() { return { ingested: false }; },
      async compact(params) { return await delegateCompactionToRuntime(params); },
      async assemble({ messages, prompt, sessionId, sessionKey, availableTools, citationsMode }) {
        const result = {
          messages,
          estimatedTokens: 0,
          systemPromptAddition: buildMemorySystemPromptAddition({
            availableTools: availableTools ?? new Set(),
            citationsMode,
            agentSessionKey: sessionKey,
          }),
        };
        if (sessionKey !== SESSION_KEY) return result;
        const turn = recallTurn;
        recallTurn = undefined;
        if (!turn || turn.sessionId !== sessionId
            || turn.admission.text !== prompt
            || pendingMessages.get(turn.deliveryId) !== turn.admission) return result;
        try {
          const quoted = await withSidecar(async (request, binding) => {
            await ensureResumed(request, binding);
            return recalledUserData(await request("/v1/runtime/source/recall", {
              task_id: TASK_ID, source, exclude_delivery_id: turn.deliveryId,
            }));
          });
          if (quoted !== undefined && pendingMessages.get(turn.deliveryId) === turn.admission) {
            // Prompt hooks persist their text in native replay. Assembly's
            // isolated message view keeps the quote at user data privilege.
            result.messages = [...messages, {
              role: "user", content: [{ type: "text", text: quoted }], timestamp: Date.now(),
            }];
          }
        } catch {
          api.logger.warn("Memorii source recall unavailable");
        }
        return result;
      },
    }));

    api.on("session_start", async (_event, context) => {
      if (context?.sessionKey !== SESSION_KEY) return;
      try {
        await withSidecar(ensureResumed);
      } catch {
        throw new Error("Memorii session resume unavailable");
      }
    });

    api.on("before_message_write", (event, context) => {
      if (context?.sessionKey !== SESSION_KEY) return;
      const message = event?.message;
      const idempotencyKey = message?.idempotencyKey;
      if (typeof idempotencyKey !== "string" || !idempotencyKey) return;
      recallTurn = undefined;
      const { role, content, provenance, display, excludeFromContext } = message;
      if (role !== "user" || provenance || display === false || excludeFromContext
          || typeof content !== "string" || !content.trim()) {
        pendingMessages.delete(idempotencyKey);
        return;
      }
      // The pinned gateway correlates this native identity with the prompt run.
      const previous = pendingMessages.get(idempotencyKey);
      if (previous) {
        if (previous.text !== content) {
          pendingMessages.delete(idempotencyKey);
          api.logger.warn("Memorii capture outcome unknown (native identity conflict)");
        }
        return;
      }
      if (pendingMessages.size >= MAX_PENDING_MESSAGES) {
        api.logger.warn("Memorii capture outcome unknown (local pending limit)");
        return;
      }
      pendingMessages.set(idempotencyKey, { text: content });
    });

    api.on("agent_end", (_event, context) => {
      if (context?.sessionKey === SESSION_KEY && recallTurn?.deliveryId === `${context.runId}:user`) {
        recallTurn = undefined;
      }
    });

    api.on("before_prompt_build", async (_event, context) => {
      const deliveryId = localDeliveryId(context);
      const admission = pendingMessages.get(deliveryId);
      if (!admission) return;
      try {
        await withSidecar(async (request, binding) => {
          await ensureResumed(request, binding);
          if (pendingMessages.get(deliveryId) !== admission) return;
          const receipt = await request("/v1/runtime/source/capture", {
            task_id: TASK_ID, source, delivery_id: deliveryId, text: admission.text,
          });
          if (!capturedObservation(receipt, TASK_ID)) throw new Error("Memorii capture receipt unavailable");
          if (pendingMessages.get(deliveryId) === admission) pendingMessages.delete(deliveryId);
        });
      } catch {
        api.logger.warn("Memorii source capture outcome unknown");
      }
    });
  },
});

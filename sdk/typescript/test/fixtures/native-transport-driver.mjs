import { registerHooks } from "node:module";

const [host, action] = process.argv.slice(2);
const hooks = new Map();
const warnings = [];
let contextEngine;
const register = (name, handle) => hooks.set(name, handle);
const nativeRoot = new URL("../../../../memorii/memorii/integrations/", import.meta.url);
const message = { role: "user", content: "original native message" };
const context = {
  sessionKey: "session:test",
  trigger: "user",
  runId: "persisted",
  sessionId: "session-id:test",
  hasUI: true,
  ui: { notify: (warning) => warnings.push(warning) },
  sessionManager: {
    getSessionId: () => "session:test",
    getBranch: () => [{ type: "message", message, id: "persisted-user" }],
  },
};

if (host === "openclaw") {
  registerHooks({
    resolve(specifier, context, nextResolve) {
      if (specifier === "openclaw/plugin-sdk/plugin-entry") {
        return {
          shortCircuit: true,
          url: "data:text/javascript,export%20const%20definePluginEntry%3Dvalue%3D%3Evalue",
        };
      }
      if (specifier === "openclaw/plugin-sdk/core") {
        return {
          shortCircuit: true,
          url: `data:text/javascript,${encodeURIComponent(`
            export const buildMemorySystemPromptAddition = () => undefined;
            export const delegateCompactionToRuntime = () => ({ ok: true });
          `)}`,
        };
      }
      return nextResolve(specifier, context);
    },
  });
  const { default: plugin } = await import(new URL("openclaw/plugin/index.js", nativeRoot));
  plugin.register({
    on: register,
    registerContextEngine: (_name, create) => { contextEngine = create(); },
    logger: { warn: (warning) => warnings.push(warning) },
  });
} else {
  const { default: extension } = await import(new URL("pi/extension/memorii-extension.ts", nativeRoot));
  extension({ on: register });
}

if (action === "resume") {
  try {
    await hooks.get("session_start")({}, context);
    console.log("resume-accepted");
  } catch {
    console.log("resume-unavailable");
  }
} else if (host === "openclaw" && action === "forwarded") {
  await hooks.get("session_start")({}, context);
  const write = hooks.get("before_message_write");
  const native = { ...message, idempotencyKey: "persisted:user" };
  await write({ message: native }, context);
  await write({ message: { ...native, provenance: { kind: "inter_session" } } }, context);
  await hooks.get("before_model_resolve")({ prompt: message.content }, context);
  const result = await contextEngine.assemble({
    messages: [message], prompt: message.content, sessionId: context.sessionId, sessionKey: context.sessionKey,
  });
  await hooks.get("before_prompt_build")({ prompt: message.content }, context);
  console.log(result.messages.length);
} else if (host === "openclaw" && action === "recover-after-outage") {
  await hooks.get("session_start")({}, context);
  for (let index = 0; index < 17; index++) {
    const unavailable = { ...context, runId: `unavailable-${index}` };
    await hooks.get("before_message_write")({
      message: { ...message, idempotencyKey: `${unavailable.runId}:user` },
    }, unavailable);
    await hooks.get("before_prompt_build")({ prompt: message.content }, unavailable);
    await hooks.get("agent_end")({}, unavailable);
  }
  const recovered = { ...context, runId: "recovered" };
  await hooks.get("before_message_write")({ message: { ...message, idempotencyKey: "recovered:user" } }, recovered);
  await hooks.get("before_model_resolve")({ prompt: message.content }, recovered);
  const result = await contextEngine.assemble({
    messages: [message], prompt: message.content, sessionId: context.sessionId, sessionKey: context.sessionKey,
  });
  await hooks.get("before_prompt_build")({ prompt: message.content }, recovered);
  console.log(JSON.stringify({ assembled: result.messages.length, failures: warnings.length }));
} else {
  await hooks.get("session_start")({}, context);
  const event = host === "pi" ? "message_end" : "before_message_write";
  const capture = host === "pi" ? "agent_end" : "before_prompt_build";
  hooks.get(event)({ message: host === "pi" ? message : { ...message, idempotencyKey: "persisted:user" } }, context);
  for (let attempt = 0; attempt < 3; attempt++) await hooks.get(capture)({}, context);
  console.log(warnings.join("\n"));
}

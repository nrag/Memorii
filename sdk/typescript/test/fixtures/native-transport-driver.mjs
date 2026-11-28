import { registerHooks } from "node:module";

const [host, action] = process.argv.slice(2);
const hooks = new Map();
const warnings = [];
const register = (name, handle) => hooks.set(name, handle);
const nativeRoot = new URL("../../../../memorii/memorii/integrations/", import.meta.url);
const message = { role: "user", content: "original native message" };
const context = {
  sessionKey: "session:test",
  trigger: "user",
  runId: "persisted",
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
      return nextResolve(specifier, context);
    },
  });
  const { default: plugin } = await import(new URL("openclaw/plugin/index.js", nativeRoot));
  plugin.register({ on: register, logger: { warn: (warning) => warnings.push(warning) } });
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
} else {
  await hooks.get("session_start")({}, context);
  const event = host === "pi" ? "message_end" : "before_message_write";
  const capture = host === "pi" ? "agent_end" : "before_prompt_build";
  hooks.get(event)({ message: host === "pi" ? message : { ...message, idempotencyKey: "persisted:user" } }, context);
  for (let attempt = 0; attempt < 3; attempt++) await hooks.get(capture)({}, context);
  console.log(warnings.join("\n"));
}

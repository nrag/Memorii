// In-container driver: loads the Memorii OpenClaw plugin with a mock host
// and fires its registered hooks in order — a resume on session start, an
// assistant transcript write (classified out), a user transcript write
// (captured), and a tool dispatch.
import plugin from "/root/.openclaw/extensions/memorii/index.js";

const handlers = [];
const api = { on: (name, handler) => handlers.push([name, handler]) };
plugin.register(api);

for (const [name, handler] of handlers) {
  if (name === "before_message_write") {
    await handler({ message: { role: "assistant", content: "derived" } });
    await handler({ message: { role: "user", content: "authentic" } });
  } else if (name === "session_start") {
    await handler({});
  } else if (name === "before_tool_call") {
    await handler({});
  } else {
    await handler({});
  }
}
console.log("plugin hooks fired:", handlers.map(([name]) => name).join(","));

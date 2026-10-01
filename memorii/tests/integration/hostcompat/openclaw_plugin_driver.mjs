// In-container driver: registers the Memorii OpenClaw plugin with a mock
// host and fires the permitted hooks in order, including one forwarded
// input that must be classified out (never submitted as evidence).
import { register } from "/opt/memorii-openclaw/plugin/index.js";

const fired = [];
const host = {
  memorySlot: () => "memorii",
  on: (name, handler) => fired.push([name, handler]),
};
register(host);

const sender = { channel_id: "channel:1", account_id: "account:1", sender_id: "sender:1" };
for (const [name, handler] of fired) {
  if (name === "prompt_inject") {
    // First a forwarded input (must be ignored), then an eligible message.
    await handler({ input_kind: "forwarded", sender });
    await handler({ input_kind: "user_message", sender });
  } else {
    await handler({});
  }
}
console.log("plugin hooks fired:", fired.map(([name]) => name).join(","));

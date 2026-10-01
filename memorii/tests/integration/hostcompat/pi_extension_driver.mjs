// In-container driver: loads the Memorii Pi extension through Node's
// native type stripping and fires its registered handlers in order. The
// extension itself owns all sidecar interaction.
import memoriiExtension from "/opt/memorii-pi/.pi/extensions/memorii-extension.ts";

const handlers = [];
const pi = { on: (name, handler) => handlers.push([name, handler]) };
memoriiExtension(pi);
for (const [name, handler] of handlers) {
  await handler({});
}
console.log("extension handlers fired:", handlers.map(([name]) => name).join(","));

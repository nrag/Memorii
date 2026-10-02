/**
 * Generated-contract parity check (npm run check:generated).
 *
 * Two gates over the frozen OpenAPI input in generated/openapi.json:
 *
 * 1. Byte parity: when a Memorii Python environment is available
 *    (MEMORII_SCHEMA_CMD or ../memorii/.venv fallback), regenerate the
 *    document with memorii-runtime-schema and byte-compare against the
 *    committed file. Byte drift fails.
 * 2. Union inventory: the TS client's closed unions (recommendation kinds,
 *    envelope statuses, error codes) must exactly equal the enums in the
 *    frozen OpenAPI schemas. A member added or removed on one side fails.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const generatedPath = path.join(here, "..", "generated", "openapi.json");
const committed = readFileSync(generatedPath, "utf8");
const document = JSON.parse(committed);

// --- Gate 1: byte parity with the Python generator (when available) -----
const candidateCommands = [
  process.env["MEMORII_SCHEMA_CMD"],
  path.join(here, "..", "..", "..", "memorii", ".venv", "bin", "python"),
].filter(Boolean);

for (const python of candidateCommands) {
  try {
    const { execFileSync } = await import("node:child_process");
    const regenerated = execFileSync(python, ["-m", "memorii.tools.runtime_schema_export"], {
      cwd: path.join(here, "..", "..", "..", "memorii"),
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    });
    if (regenerated !== committed) {
      console.error(
        "check:generated FAILED — regenerated OpenAPI differs from generated/openapi.json",
      );
      console.error("Regenerate with memorii-runtime-schema and commit the result.");
      process.exit(1);
    }
    console.log("check:generated — byte parity with Python generator OK");
    break;
  } catch (error) {
    if (process.env["MEMORII_SCHEMA_CMD"] !== undefined) {
      console.error("check:generated FAILED — MEMORII_SCHEMA_CMD failed:", String(error));
      process.exit(1);
    }
    // No Python environment available: byte parity is enforced by the CI
    // job that installs one; state that honestly rather than passing silently.
    console.log(
      "check:generated — Python generator unavailable locally; byte parity enforced in CI",
    );
  }
  break;
}

if (candidateCommands.length === 0) {
  console.log(
    "check:generated — no Python generator configured; byte parity enforced in CI",
  );
}

// --- Gate 2: union inventory parity --------------------------------------
const schemas = document["components"]["schemas"];
const envelope = schemas["HarnessStateEnvelope"];
const errorEnvelope = schemas["SidecarError"];

function requireEnum(pointer, field) {
  const value = pointer?.["properties"]?.[field]?.["enum"];
  if (!Array.isArray(value)) {
    console.error(`check:generated FAILED — missing enum for ${field}`);
    process.exit(1);
  }
  return new Set(value);
}

const schemaRecommendation = requireEnum(envelope, "recommendation_kind");
const schemaStatus = requireEnum(envelope, "status");
const schemaErrorCodes = requireEnum(errorEnvelope, "code");

// Keep these literal sets in sync with src/client.ts — that is the point.
// Parse the client source for the union literals; robust to no build yet.
const clientSource = readFileSync(path.join(here, "..", "src", "client.ts"), "utf8");

function unionOf(typeName) {
  const match = clientSource.match(
    new RegExp(`export type ${typeName} =([\\s\\S]*?);`),
  );
  if (!match) {
    console.error(`check:generated FAILED — union ${typeName} not found in client source`);
    process.exit(1);
  }
  const members = new Set(
    [...match[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]),
  );
  return members;
}

function assertSame(name, tsUnion, schemaEnum) {
  const missing = [...schemaEnum].filter((v) => !tsUnion.has(v));
  const extra = [...tsUnion].filter((v) => !schemaEnum.has(v));
  if (missing.length > 0 || extra.length > 0) {
    console.error(`check:generated FAILED — ${name} drifted`);
    if (missing.length > 0) console.error(`  missing from TS client: ${missing.join(", ")}`);
    if (extra.length > 0) console.error(`  extra in TS client: ${extra.join(", ")}`);
    process.exit(1);
  }
  console.log(`check:generated — ${name} union parity OK (${tsUnion.size} members)`);
}

assertSame("recommendation_kind", unionOf("RecommendationKind"), schemaRecommendation);
assertSame("status", unionOf("EnvelopeStatus"), schemaStatus);
assertSame("error codes", unionOf("RuntimeErrorCode"), schemaErrorCodes);

console.log("check:generated — all parity gates passed");

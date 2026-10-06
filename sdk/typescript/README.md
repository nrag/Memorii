# @memorii/runtime-client

Typed TypeScript client for the Memorii loopback runtime sidecar
(protocol v1). Mirrors the Python `RuntimeStateClient` contract: the
same closed v1 state request, the same error codes, loopback-only
binding.

## Supported runtimes

- Node.js 24 through 26 (`engines: ">=24.0.0 <27.0.0"`)
- npm 11 or later

Install-time, npm enforces the `engines` range against the running
Node: outside the range npm refuses the install with the detected
version and the supported window. Runtime protocol violations surface
the sidecar's `unsupported_version` error code via `RuntimeClientError`
— never silent degradation.

## Usage

```ts
import { RuntimeStateClient } from "@memorii/runtime-client";

const client = new RuntimeStateClient({
  baseUrl: "http://127.0.0.1:8734", // loopback sidecar only
  credential: process.env["MEMORII_CREDENTIAL"] ?? "",
});

const state = await client.getState("task:one");
// state.status, state.recommendation_kind, state.pending_actions, ...

// Paged frontier continuation: pass the cursor from the previous page.
if (state.continuation_cursor) {
  const next = await client.getState("task:one", {
    cursor: state.continuation_cursor,
  });
}
```

Credentials are installation-issued bearer tokens; they are sent only in
the `Authorization` header, never in URLs or logs.

## Development

```bash
npm ci                  # reproducible install from the lockfile
npm run check:generated # schema byte parity + closed-union inventory
npm run typecheck
npm test
npm run build
npm pack --dry-run
npm run test:installed  # installs the tarball outside the checkout and smokes it
```

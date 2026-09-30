"""Generate the closed HTTP/OpenAPI schema for the runtime v1 surface.

The generator derives the OpenAPI document from the same typed models
the embedded path and the sidecar use — SidecarRequest, the envelope,
and the closed error envelope — so no hand-written schema can drift.
Output is deterministic (sorted keys, fixed order) and byte-stable for
a given model set; the release gate pins its digest.
"""

from __future__ import annotations

import argparse
import json
import sys


def build_openapi_document() -> dict[str, object]:
    from memorii.core.harness_state.envelope import HarnessStateEnvelope
    from memorii.core.harness_state.sidecar import SidecarError, SidecarRequest

    def schema(model: type) -> dict[str, object]:
        return json.loads(
            json.dumps(model.model_json_schema(), sort_keys=True)
        )

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Memorii Runtime Sidecar",
            "version": "1.0.0",
            "description": (
                "Loopback runtime sidecar: closed v1 state requests over the"
                " verified partition. Transport posture: loopback bind,"
                " browser-origin rejection, installation-issued bearer"
                " credentials."
            ),
        },
        "servers": [{"url": "http://127.0.0.1", "description": "loopback only"}],
        "paths": {
            "/v1/runtime/state": {
                "post": {
                    "operationId": "readRuntimeState",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SidecarRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Authorized bounded envelope",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/HarnessStateEnvelope"
                                    }
                                }
                            },
                        },
                        "default": {
                            "description": "Closed error envelope (no task-derived data)",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/SidecarError"}
                                }
                            },
                        },
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            },
            "schemas": {
                "SidecarRequest": schema(SidecarRequest),
                "HarnessStateEnvelope": schema(HarnessStateEnvelope),
                "SidecarError": schema(SidecarError),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memorii-runtime-schema",
        description="Emit the deterministic OpenAPI schema for the runtime sidecar.",
    )
    parser.add_argument("--output", type=str, default="-")
    arguments = parser.parse_args(argv)
    document = build_openapi_document()
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output == "-":
        sys.stdout.write(text)
    else:
        with open(arguments.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

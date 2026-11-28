"""Diagnostic output shared by Memorii's runtime command-line tools."""

from __future__ import annotations

import argparse


class SafeArgumentParser(argparse.ArgumentParser):
    """Keep rejected command-line values out of usage diagnostics."""

    def error(self, message: str) -> None:
        super().error("invalid arguments; see --help")


def diagnostic_code(error: RuntimeError) -> str:
    """Preserve recognized outcomes without rendering the attached detail."""
    code = str(error).partition(":")[0]
    if code in {
        "conflict",
        "denied",
        "integrity_error",
        "invalid_request",
        "needs_reconciliation",
        "resource_exhausted",
        "unsupported_configuration",
    }:
        return code
    return "unavailable"

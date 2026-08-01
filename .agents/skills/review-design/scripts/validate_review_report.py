#!/usr/bin/env python3
"""Validate the structural completeness of a Memorii design-review report."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_SECTIONS = (
    "Review Metadata",
    "Executive Assessment",
    "Governing Sources",
    "Independently Reconstructed Requirements",
    "Contract And Evidence Boundaries",
    "Confirmed Findings",
    "Requirements Coverage",
    "Architecture And Feasibility",
    "Failure, Security, And Operations",
    "Verification And Evidence Maturity",
    "Risk Register",
    "Rejected Or Consolidated Findings",
    "Required Changes Before Approval",
    "Non-Blocking Follow-Ups",
    "Final Outcome",
    "Review Limitations",
)

REQUIRED_FINDING_FIELDS = (
    "Product priority",
    "Approval disposition",
    "Remediation eligibility",
    "Confidence",
    "Finding type",
    "Affected scenario and prevalence evidence",
    "Design location",
    "Governing source or requirement",
    "Expected behavior",
    "Design behavior",
    "Evidence",
    "Impact",
    "Root invariant or contract boundary",
    "Equivalence class and adjacent bypasses inspected",
    "Positive behavior that must remain valid",
    "Recommended invariant-level resolution",
    "Verification needed",
    "Evidence maturity affected",
)


def validate_report(text: str) -> list[str]:
    errors: list[str] = []
    for section in REQUIRED_SECTIONS:
        if not re.search(rf"^## {re.escape(section)}\s*$", text, re.MULTILINE):
            errors.append(f"missing section: {section}")

    finding_starts = list(
        re.finditer(r"^### (DREV-\d{3}): .+$", text, re.MULTILINE)
    )
    for index, match in enumerate(finding_starts):
        end = finding_starts[index + 1].start() if index + 1 < len(finding_starts) else len(text)
        block = text[match.end() : end]
        for field in REQUIRED_FINDING_FIELDS:
            if not re.search(rf"^- {re.escape(field)}:\s*.+$", block, re.MULTILINE):
                errors.append(f"{match.group(1)} missing populated field: {field}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    errors = validate_report(args.report.read_text(encoding="utf-8"))
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"review report structure valid: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

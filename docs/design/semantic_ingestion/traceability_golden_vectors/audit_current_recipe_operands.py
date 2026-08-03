"""Emit the complete operand-closure audit for the current scenario-first closure recipe.

This intentionally performs no derivation.  It records the exact derived
leaves that the recipe asks an elaborator to synthesize without naming their
operands, so an authority review cannot mistake formula-family labels for a
topologically valid derivation program.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii") + b"\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    recipe = json.loads(args.recipe.read_bytes())
    ledger = recipe["primitive_authority"]["body_leaf_classification"]
    missing_by_rule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    derived_total = 0
    present_total = 0
    for fixture_id in sorted(ledger):
        for entry in ledger[fixture_id]:
            if entry["source"] != "deterministic_derivation":
                continue
            derived_total += 1
            if "operands" in entry:
                present_total += 1
                continue
            missing_by_rule[entry["derivation_rule_id"]].append(
                {"fixture_id": fixture_id, "path": entry["path"]}
            )

    audit = {
        "format": "memorii-sia-operand-closure-audit-v1",
        "derived_leaf_count": derived_total,
        "derived_leaves_with_explicit_operands": present_total,
        "missing_operands_by_formula_id": {
            rule_id: missing_by_rule[rule_id] for rule_id in sorted(missing_by_rule)
        },
    }
    args.output.write_bytes(canonical(audit))


if __name__ == "__main__":
    main()

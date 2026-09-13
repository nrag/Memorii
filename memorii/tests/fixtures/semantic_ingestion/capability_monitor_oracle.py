"""Independent standard-library oracle for the frozen monitor confidence vector."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, localcontext
from pathlib import Path


def main() -> int:
    fixture = json.loads(Path(sys.argv[1]).read_text(encoding="ascii"))
    values = tuple(Decimal(value) for value in fixture["values"])
    lower = Decimal(fixture["bounded_value_lower"])
    upper = Decimal(fixture["bounded_value_upper"])
    alpha = Decimal(fixture["alpha_budget"])
    with localcontext() as context:
        context.prec = 50
        count = Decimal(len(values))
        estimate = sum(values, Decimal(0)) / count
        allocated = alpha / (count * (count + 1))
        radius = (-(allocated / Decimal(2)).ln() / (Decimal(2) * count)).sqrt()
        result = {
            "estimate": str(estimate.normalize()),
            "lower_bound": str(max(lower, estimate - radius).normalize()),
            "upper_bound": str(min(upper, estimate + radius).normalize()),
        }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

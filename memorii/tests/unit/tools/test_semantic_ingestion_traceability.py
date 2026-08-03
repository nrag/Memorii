from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from memorii.tools.semantic_ingestion_traceability import UnitRequirementMapping, extract_normative_units
from memorii.tools.semantic_ingestion_traceability_checker import (
    TraceabilityCoverageError,
    verify_traceability_coverage,
)

_DESIGN = b"""# Frozen Design

## 1. One

The first contract.

- one rule
- two rule

| ID | Owner |
| --- | --- |
| SIA-R03 | acceptance |

```python
class Contract:
    field: str
```

## 2. Two

The second contract.

## 5. Five

The final contract.
"""


def _mappings():
    units = extract_normative_units(_DESIGN)
    return units, tuple(
        UnitRequirementMapping(
            invariant_id=unit.invariant_id,
            content_key=unit.content_key,
            requirement_id="SIA-R03",
            owner="acceptance",
            assertion_id=f"assert-{index}",
            assertion_version=1,
            test_evidence_group="SIA-T03-STRUCT",
        )
        for index, unit in enumerate(units)
    )


def test_traceability_accepts_complete_closed_coverage() -> None:
    units, mappings = _mappings()
    verify_traceability_coverage(
        design_bytes=_DESIGN,
        published_units=units,
        mappings=mappings,
        requirements_to_owners={"SIA-R03": "acceptance"},
    )


def test_traceability_extracts_every_closed_grammar_unit_from_frozen_design() -> None:
    design = Path(__file__).parents[4] / "docs" / "design" / "semantic_ingestion_architecture.md"
    units = extract_normative_units(design.read_bytes())
    assert len(units) > 7_000
    assert {unit.unit_kind for unit in units} >= {"heading", "paragraph", "list", "table", "fence", "code_line"}
    emitted_ids = {unit.invariant_id for unit in units}
    assert all(unit.parent_invariant_id is None or unit.parent_invariant_id in emitted_ids for unit in units)


def test_traceability_direct_parents_are_emitted_structural_units() -> None:
    units = extract_normative_units(_DESIGN)
    by_kind = {unit.unit_kind: unit for unit in units}
    assert by_kind["list_item"].parent_invariant_id == by_kind["list"].invariant_id
    assert by_kind["table_row"].parent_invariant_id == by_kind["table"].invariant_id
    assert by_kind["schema_declaration"].parent_invariant_id == by_kind["fence"].invariant_id
    assert by_kind["schema_field"].parent_invariant_id == by_kind["fence"].invariant_id


def test_traceability_repeated_headings_keep_their_own_parent_occurrences() -> None:
    repeated = b"""# Frozen Design

## 1. One

### 1.1 Repeat

first child.

### 1.1 Repeat

#### 1.1.1 Nested

second child.

## 5. Five
"""
    units = extract_normative_units(repeated)
    headings = [unit for unit in units if unit.unit_kind == "heading"]
    repeats = [unit for unit in headings if unit.source_start_line in {5, 9}]
    assert len(repeats) == 2
    assert repeats[0].invariant_id != repeats[1].invariant_id
    nested = next(unit for unit in headings if unit.source_start_line == 11)
    second_paragraph = next(unit for unit in units if unit.unit_kind == "paragraph" and unit.source_start_line == 13)
    assert nested.parent_invariant_id == repeats[1].invariant_id
    assert second_paragraph.parent_invariant_id == nested.invariant_id
    verify_traceability_coverage(
        design_bytes=repeated,
        published_units=units,
        mappings=tuple(
            UnitRequirementMapping(
                invariant_id=unit.invariant_id,
                content_key=unit.content_key,
                requirement_id="SIA-R03",
                owner="acceptance",
                assertion_id="duplicate-parent",
                assertion_version=1,
                test_evidence_group="SIA-T03-STRUCT",
            )
            for unit in units
        ),
        requirements_to_owners={"SIA-R03": "acceptance"},
    )


def test_traceability_excludes_non_normative_sections() -> None:
    with_section_six = _DESIGN + b"\n## 6. Excluded\n\nThis must not be extracted.\n"
    before = extract_normative_units(_DESIGN)
    after = extract_normative_units(with_section_six)
    assert after == before


@pytest.mark.parametrize("mutation", ["missing", "orphan", "duplicate", "wrong_owner", "stale_unit", "stale_parent"])
def test_traceability_rejects_incomplete_or_forged_coverage(mutation: str) -> None:
    units, mappings = _mappings()
    if mutation == "missing":
        mappings = mappings[1:]
    elif mutation == "orphan":
        mappings = (*mappings, replace(mappings[0], invariant_id="SIA-N-missing-0"))
    elif mutation == "duplicate":
        mappings = (*mappings, mappings[0])
    elif mutation == "wrong_owner":
        mappings = (replace(mappings[0], owner="wrong"), *mappings[1:])
    elif mutation == "stale_unit":
        units = (*units[:-1], replace(units[-1], content_key="0" * 64))
    else:
        child = next(unit for unit in units if unit.parent_invariant_id is not None)
        position = units.index(child)
        units = (*units[:position], replace(child, parent_invariant_id="SIA-N-missing-0"), *units[position + 1 :])
    with pytest.raises(TraceabilityCoverageError):
        verify_traceability_coverage(
            design_bytes=_DESIGN,
            published_units=units,
            mappings=mappings,
            requirements_to_owners={"SIA-R03": "acceptance"},
        )

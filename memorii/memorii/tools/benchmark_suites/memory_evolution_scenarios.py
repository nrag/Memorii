"""Shared scenario loading for simulator and runtime memory-evolution suites."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    generate_memory_evolution_sim_scenarios,
)


def load_memory_evolution_scenarios(
    args: argparse.Namespace,
) -> tuple[list[LatentGraphScenario], str]:
    """Load one latent scenario surface consumed by both benchmark suites."""

    if args.sim_fixture_path:
        payload = json.loads(Path(args.sim_fixture_path).read_text(encoding="utf-8"))
        return (
            [LatentGraphScenario.model_validate(item) for item in payload],
            str(args.sim_fixture_path),
        )
    return (
        generate_memory_evolution_sim_scenarios(
            profile=args.sim_profile,
            scenario_count=args.sim_scenario_count,
            seed=args.seed,
            min_events=args.sim_min_events,
            max_events=args.sim_max_events,
            noise_rate=args.sim_noise_rate,
        ),
        f"generated:{args.sim_profile}:seed={args.seed}",
    )

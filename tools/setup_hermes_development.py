#!/usr/bin/env python3
"""Connect a Hermes development environment to Memorii before release signing."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(arguments: list[str], *, environment: dict[str, str] | None = None) -> None:
    completed = subprocess.run(arguments, check=False, env=environment)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(arguments)}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hermes-python",
        type=Path,
        help="Python executable used by Hermes (auto-detected for managed installs)",
    )
    parser.add_argument(
        "--hermes-command",
        default="hermes",
        help="Hermes executable used to update and inspect its configuration",
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="install and verify the connector without changing Hermes configuration",
    )
    return parser


def _hermes_python(configured: Path | None) -> Path:
    if configured is not None:
        candidates = (configured,)
    else:
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        environment_value = os.environ.get("HERMES_PYTHON")
        candidates = tuple(
            candidate
            for candidate in (
                Path(environment_value) if environment_value else None,
                hermes_home / "hermes-agent" / "venv" / "bin" / "python",
                hermes_home / "hermes-agent" / ".venv" / "bin" / "python",
                Path(sys.executable),
            )
            if candidate is not None
        )
    for candidate in candidates:
        path = candidate.expanduser().absolute()
        if path.is_file():
            return path
    raise ValueError("could not find the Hermes Python executable; pass --hermes-python")


def _install(python: Path, packages: tuple[Path, ...]) -> None:
    pip_probe = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    editable = [item for package in packages for item in ("--editable", str(package))]
    if pip_probe.returncode == 0:
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-build-isolation",
                *editable,
            ]
        )
        return
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Hermes Python has no pip and uv is unavailable")
    _run([uv, "pip", "install", "--python", str(python), *editable])


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    memorii_package = repository / "memorii"
    connector = repository / "tools" / "hermes_development_connector"
    python = _hermes_python(args.hermes_python)
    _install(python, (memorii_package, connector))

    probe = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import json; from memorii_hermes_development import probe; "
                "print(json.dumps(probe()))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise RuntimeError(probe.stderr.strip() or "Hermes development connector probe failed")
    status = json.loads(probe.stdout)
    if (
        status.get("development_factory_count") != 1
        or not status.get("memorii_provider_installed")
        or not status.get("hermes_abc_installed")
    ):
        raise RuntimeError(f"Hermes development connector is incomplete: {status}")

    if not args.skip_config:
        environment = dict(os.environ)
        _run(
            [args.hermes_command, "config", "set", "memory.provider", "memorii"],
            environment=environment,
        )
        _run([args.hermes_command, "memory", "status"], environment=environment)

    print(
        json.dumps(
            {
                "status": "ready",
                "hermes_python": str(python),
                "provider": "memorii",
                "production_signing": False,
                "next_command": args.hermes_command,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

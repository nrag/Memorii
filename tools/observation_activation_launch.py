"""Launch a protected host only after verifying its offline deployment.

Invoke with -I -S -X pycache_prefix=NEW_PRIVATE_DIRECTORY. The launcher and
its SHA256 arguments are protected host inputs, never runtime request values.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import stat
import sys
from hashlib import sha256
from pathlib import Path


def _load_pinned_module(name: str, path: Path, expected_sha256: str):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 128 * 1024**2:
            raise ValueError("protected_module_file_invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            source = stream.read(128 * 1024**2 + 1)
        if len(source) != info.st_size or sha256(source).hexdigest() != expected_sha256:
            raise ValueError("protected_module_digest_mismatch")
    finally:
        os.close(descriptor)
    if name in sys.modules:
        raise ValueError("protected_module_already_loaded")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise ValueError("protected_module_spec_invalid")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("bootstrap", "configuration", "host"):
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-sha256", required=True)
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.no_site or sys.pycache_prefix is None:
        parser.error("requires -I -S -X pycache_prefix=NEW_PRIVATE_DIRECTORY")
    bootstrap = _load_pinned_module("observation_activation_bootstrap", args.bootstrap, args.bootstrap_sha256)
    configuration = _load_pinned_module("deployment_configuration", args.configuration, args.configuration_sha256).configuration
    sys.path.insert(0, str(configuration.installation_root))
    facts = bootstrap.verify_deployment(configuration, private_pycache_prefix=Path(sys.pycache_prefix))
    bootstrap.install_selected_distribution_origin_guard(configuration)
    host = _load_pinned_module("observation_activation_host", args.host, args.host_sha256)
    result = host.main(configuration, facts)
    if type(result) is not int:
        raise ValueError("protected_host_exit_code_invalid")
    return result


if __name__ == "__main__":
    raise SystemExit(main())

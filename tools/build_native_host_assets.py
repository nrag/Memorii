"""Build reproducible, separately distributable native host assets."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import tarfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HostSource:
    name: str
    directory: str
    dependency: str
    members: tuple[str, ...]


_HOSTS = (
    HostSource(
        "pi",
        "pi/extension",
        "@earendil-works/pi-coding-agent",
        (
            "internal/sidecar-transport.d.ts",
            "internal/sidecar-transport.js",
            "memorii-extension.ts",
            "package-lock.json",
            "package.json",
        ),
    ),
    HostSource(
        "openclaw",
        "openclaw/plugin",
        "openclaw",
        (
            "index.js",
            "internal/sidecar-transport.js",
            "openclaw.plugin.json",
            "package-lock.json",
            "package.json",
        ),
    ),
)


@dataclass(frozen=True)
class AssetFile:
    filename: str
    sha256: str


@dataclass(frozen=True)
class HostAsset:
    host: str
    host_package: str
    host_version: str
    archive: AssetFile
    members: tuple[AssetFile, ...]


@dataclass(frozen=True)
class HostAssetManifest:
    schema_version: int
    source_revision: str
    wheel: AssetFile
    hosts: tuple[HostAsset, ...]


def _sha256(path: Path) -> str:
    with path.open("rb") as contents:
        return hashlib.file_digest(contents, "sha256").hexdigest()


def _build_host(root: Path, output: Path, host: HostSource) -> HostAsset:
    source = root / "memorii" / "memorii" / "integrations" / host.directory
    package = json.loads((source / "package.json").read_bytes())
    lock = json.loads((source / "package-lock.json").read_bytes())
    version = package["dependencies"][host.dependency]
    if re.fullmatch(r"\d+\.\d+\.\d+", version) is None or (
        lock["packages"][""]["dependencies"] != package["dependencies"]
        or lock["packages"][f"node_modules/{host.dependency}"]["version"] != version
    ):
        raise ValueError(
            f"{host.name} package and lockfile must declare the same exact host pin"
        )

    archive = output / f"memorii-{host.name}-host-{version}.tar.gz"
    members: list[AssetFile] = []
    with (
        archive.open("xb") as destination,
        gzip.GzipFile(
            filename="", mode="wb", fileobj=destination, mtime=0
        ) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
        ) as bundle,
    ):
        for filename in host.members:
            original = source / filename
            if (
                original.is_symlink()
                or not original.is_file()
                or not original.resolve().is_relative_to(source.resolve())
            ):
                raise ValueError(f"unsafe native host source member {filename}")
            contents = original.read_bytes()
            item = tarfile.TarInfo(filename)
            item.size = len(contents)
            item.mode = 0o644
            bundle.addfile(item, io.BytesIO(contents))
            members.append(AssetFile(filename, hashlib.sha256(contents).hexdigest()))
    return HostAsset(
        host.name,
        host.dependency,
        version,
        AssetFile(archive.name, _sha256(archive)),
        tuple(members),
    )


def build_assets(
    root: Path, *, wheel: Path, output: Path, revision: str
) -> HostAssetManifest:
    if re.fullmatch(r"[a-f0-9]{40}", revision) is None:
        raise ValueError("host assets require a full source commit SHA")
    if wheel.suffix != ".whl" or not wheel.is_file() or wheel.is_symlink():
        raise ValueError("host assets require the regular candidate wheel file")
    output.mkdir()
    manifest = HostAssetManifest(
        1,
        revision,
        AssetFile(wheel.name, _sha256(wheel)),
        tuple(_build_host(root, output, host) for host in _HOSTS),
    )
    (output / "native-host-assets.json").write_text(
        json.dumps(asdict(manifest), indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    arguments = parser.parse_args()
    build_assets(
        Path(__file__).resolve().parents[1],
        wheel=arguments.wheel,
        output=arguments.output,
        revision=arguments.revision,
    )


if __name__ == "__main__":
    main()

"""Build one private native extension per pytest process."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def extension(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("retained-extension")
    library = root / "retainedvfs.dylib"
    source = Path(__file__).with_name("retained_vfs.c")
    sqlite = Path(os.environ.get("SQLITE_PREFIX", "/opt/homebrew/opt/sqlite"))
    crypto = Path(os.environ.get("OPENSSL_PREFIX", "/opt/homebrew/opt/openssl@3"))
    subprocess.run([
        "xcrun", "clang", "-std=c11", "-dynamiclib", "-Wall", "-Wextra", "-Werror",
        f"-I{sqlite / 'include'}", f"-I{crypto / 'include'}", str(source),
        f"-L{crypto / 'lib'}", "-lcrypto", "-o", str(library),
    ], check=True)
    return library

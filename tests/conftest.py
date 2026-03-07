from __future__ import annotations

import os
import shutil
from pathlib import Path
import pytest

# REQUIRED_FILES + settings loader kommen aus deinem Code:
from docflow.settings.defaults import REQUIRED_FILES

MINIMAL_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _repo_root_from_tests() -> Path:
    cur = Path(__file__).resolve()
    for _ in range(10):
        if (cur / "pyproject.toml").exists():
            return cur
        cur = cur.parent
    raise RuntimeError("Could not locate repo root from tests/ (pyproject.toml missing?)")


@pytest.fixture()
def repo_root() -> Path:
    return _repo_root_from_tests()


@pytest.fixture()
def repo_settings_dir(repo_root: Path) -> Path:
    # In deinem Projekt liegen die YAMLs in src/docflow/settings/
    p = repo_root / "src" / "docflow" / "settings"
    assert p.exists(), f"Expected settings dir at {p}"
    return p


@pytest.fixture()
def tmp_settings_dir(tmp_path: Path, repo_settings_dir: Path) -> Path:
    """
    Copy REQUIRED_FILES into a temp settings dir so tests can mutate safely.
    """
    dst = tmp_path / "settings"
    dst.mkdir(parents=True, exist_ok=True)

    for name in REQUIRED_FILES:
        src = repo_settings_dir / name
        assert src.exists(), f"Missing required settings file in repo: {src}"
        shutil.copy2(src, dst / name)

    return dst


@pytest.fixture()
def tmp_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "input.pdf"
    p.write_bytes(MINIMAL_PDF_BYTES)
    return p


@pytest.fixture()
def run_integration() -> bool:
    return os.environ.get("RUN_INTEGRATION", "0") == "1"

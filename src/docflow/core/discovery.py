from __future__ import annotations
from pathlib import Path
import re

AREA_RE = re.compile(r"^(0[1-9]|1[0-1]|98)_[A-Z0-9_]+$")


def discover_areas(archiv_root: Path) -> list[str]:
    areas = []
    for p in archiv_root.iterdir():
        if p.is_dir() and AREA_RE.match(p.name):
            areas.append(p.name)
    return sorted(areas)


def list_pdfs(inbox_dir: Path) -> list[Path]:
    return sorted([p for p in inbox_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"])

# docflow/src/docflow/core/discovery.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import AppConfig


@dataclass(frozen=True)
class Area:
    id: str
    path: Path


def areas_from_settings(cfg: AppConfig) -> List[Area]:
    """
    Closed-world: YAML defines areas, not filesystem inference.
    """
    return [
        Area(id=area_id, path=cfg.paths.archiv_root / area_id) for area_id in cfg.allowed_area_ids()
    ]


def area_path(cfg: AppConfig, area_id: str) -> Path:
    cfg.validate_area_id(area_id)
    return cfg.paths.archiv_root / area_id


def year_path(cfg: AppConfig, area_id: str, year: int) -> Path:
    cfg.validate_area_id(area_id)
    y = str(int(year))
    if not cfg.year_dir_pattern.match(y):
        raise ValueError(f"Invalid year '{year}'")
    return cfg.paths.archiv_root / area_id / y


def list_pdfs(inbox_dir: Path) -> List[Path]:
    """
    Lists PDFs in inbox root (top-level only), stable order.
    """
    p = Path(inbox_dir)
    if not p.exists():
        return []
    return sorted([x for x in p.iterdir() if x.is_file() and x.suffix.lower() == ".pdf"])

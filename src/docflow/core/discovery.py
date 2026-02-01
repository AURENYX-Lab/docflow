from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .config import AppConfig


@dataclass(frozen=True)
class Area:
    id: str
    path: Path


def areas_from_settings(cfg: AppConfig) -> List[Area]:
    """
    We do NOT infer categories from filesystem.
    The YAML settings define the closed-world list of areas.
    """
    out: List[Area] = []
    for area_id in cfg.allowed_area_ids():
        out.append(Area(id=area_id, path=cfg.paths.archiv_root / area_id))
    return out


def area_path(cfg: AppConfig, area_id: str) -> Path:
    cfg.validate_area_id(area_id)
    return cfg.paths.archiv_root / area_id


def year_path(cfg: AppConfig, area_id: str, year: int) -> Path:
    cfg.validate_area_id(area_id)
    y = str(int(year))
    if not cfg.year_dir_pattern.match(y):
        raise ValueError(f"Invalid year '{year}'")
    return cfg.paths.archiv_root / area_id / y

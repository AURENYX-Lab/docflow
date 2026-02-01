# src/docflow/settings/defaults.py
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict

import yaml

from .models import Settings, SettingsPaths


class SettingsError(RuntimeError):
    pass


REQUIRED_FILES = (
    "categories.yaml",
    "doctypes.yaml",
    "heuristics.yaml",
    "filenames.yaml",
    "pipeline.yaml",
    "prompts.yaml",
    "ocr.yaml",
)


def _read_yaml_required(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SettingsError(f"Missing required settings file: {path}")
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SettingsError(f"Failed to parse YAML: {path} ({e})") from e
    if not isinstance(obj, dict):
        raise SettingsError(f"Settings file must contain a YAML mapping/object: {path}")
    return obj


def _sha256_settings_dir(settings_dir: Path) -> str:
    h = hashlib.sha256()
    for name in REQUIRED_FILES:
        p = settings_dir / name
        h.update(p.read_bytes())
        h.update(b"\n")
    return h.hexdigest()


def load_settings(settings_dir: Path, paths: SettingsPaths) -> Settings:
    settings_dir = Path(settings_dir).expanduser().resolve()

    missing = [n for n in REQUIRED_FILES if not (settings_dir / n).exists()]
    if missing:
        raise SettingsError(
            "Missing required settings files (YAML is mandatory):\n"
            f"  settings_dir: {settings_dir}\n"
            f"  missing: {', '.join(missing)}"
        )

    raw = {name: _read_yaml_required(settings_dir / name) for name in REQUIRED_FILES}

    data = {
        "settings_dir": str(settings_dir),
        "paths": paths,
        "categories": raw["categories.yaml"],
        "doctypes": raw["doctypes.yaml"],
        "heuristics": raw["heuristics.yaml"],
        "filenames": raw["filenames.yaml"],
        "pipeline": raw["pipeline.yaml"],
        "prompts": raw["prompts.yaml"],
        "ocr": raw["ocr.yaml"],
        "settings_sha256": _sha256_settings_dir(settings_dir),
    }

    try:
        return Settings.model_validate(data)
    except Exception as e:
        raise SettingsError(f"Settings validation failed: {e}") from e

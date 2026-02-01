from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from .models import Settings, SettingsPaths


class SettingsError(RuntimeError):
    pass


SPLIT_FILES = (
    "categories.yaml",
    "heuristics.yaml",
    "filenames.yaml",
    "pipeline.yaml",
    "prompts.yaml",
    "ocr.yaml",
)

SINGLE_FILE = "docflow.yaml"


def _read_bytes(p: Path) -> bytes:
    try:
        return p.read_bytes()
    except FileNotFoundError:
        raise SettingsError(f"Missing required settings file: {p}")
    except Exception as e:
        raise SettingsError(f"Failed to read settings file {p}: {e}")


def _sha256_settings_bundle(files: Tuple[Path, ...]) -> str:
    """
    Deterministic sha: includes filenames + bytes to prevent ambiguity.
    """
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.name):
        h.update(p.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(_read_bytes(p))
        h.update(b"\x00\x00")
    return h.hexdigest()


def _yaml_load_dict(p: Path) -> Dict[str, Any]:
    raw = _read_bytes(p)
    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        raise SettingsError(f"YAML parse error in {p.name}: {e}")
    if not isinstance(data, dict):
        raise SettingsError(f"{p.name} must be a YAML mapping/object at top-level")
    return data


def load_settings(paths: SettingsPaths) -> Settings:
    settings_dir = Path(paths.settings_dir).expanduser().resolve()
    if not settings_dir.exists() or not settings_dir.is_dir():
        raise SettingsError(f"Settings dir does not exist or is not a directory: {settings_dir}")

    single = settings_dir / SINGLE_FILE
    if single.exists():
        data = _yaml_load_dict(single)
        sha = _sha256_settings_bundle((single,))
        # inject sha as required field
        data["settings_sha256"] = sha
        try:
            return Settings.model_validate(data)
        except Exception as e:
            raise SettingsError(f"Settings validation failed for {SINGLE_FILE}: {e}")

    # otherwise: require full split set
    missing = [fn for fn in SPLIT_FILES if not (settings_dir / fn).exists()]
    if missing:
        raise SettingsError(
            "No docflow.yaml found AND split settings incomplete. Missing: "
            + ", ".join(missing)
            + f" (expected in {settings_dir})"
        )

    # merge split files into one dict with strict top-level keys
    merged: Dict[str, Any] = {}
    files = tuple(settings_dir / fn for fn in SPLIT_FILES)
    sha = _sha256_settings_bundle(files)

    for fn in SPLIT_FILES:
        p = settings_dir / fn
        part = _yaml_load_dict(p)
        # each split file must contain exactly ONE top-level key matching its section
        expected_key = fn.replace(".yaml", "")
        if expected_key not in (
            "categories",
            "heuristics",
            "filenames",
            "pipeline",
            "prompts",
            "ocr",
        ):
            raise SettingsError(f"Internal error: unexpected split key {expected_key}")

        if set(part.keys()) != {expected_key}:
            raise SettingsError(
                f"{fn} must contain exactly one top-level key '{expected_key}', got keys: {list(part.keys())}"
            )
        merged[expected_key] = part[expected_key]

    merged["settings_sha256"] = sha

    try:
        return Settings.model_validate(merged)
    except Exception as e:
        raise SettingsError(f"Settings validation failed for split settings: {e}")

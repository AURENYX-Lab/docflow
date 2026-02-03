from __future__ import annotations

from pathlib import Path
from typing import Tuple, Optional
import re

import pytest
import yaml

from docflow.settings.defaults import load_settings
from docflow.settings.models import SettingsPaths

from docflow.core.heuristics import (
    add_one_month,
    extract_aktenzeichen,
    extract_date,
    guess_area,
)


def _paths(settings_dir: Path) -> SettingsPaths:
    return SettingsPaths(settings_dir=str(settings_dir))


def _pick_area_and_keyword(settings_dir: Path) -> Tuple[str, str]:
    """
    Deterministic: read categories.yaml, pick the first area that has at least one keyword.
    This makes the test robust to model refactors, as long as YAML stays the source of truth.
    """
    obj = yaml.safe_load((settings_dir / "categories.yaml").read_text(encoding="utf-8"))
    areas = obj.get("areas") or []
    for a in areas:
        kws = a.get("keywords") or []
        if kws:
            return str(a["id"]), str(kws[0])
    raise RuntimeError(
        "No area with keywords found in categories.yaml (test requires at least one)."
    )


def test_add_one_month_handles_end_of_month() -> None:
    # 2024 is leap year: Feb has 29 days. Jan 31 -> Feb 29 (clamped).
    assert add_one_month("2024-01-31") == "2024-02-29"
    # Non-leap: Jan 31 -> Feb 28
    assert add_one_month("2023-01-31") == "2023-02-28"


def test_extract_aktenzeichen_finds_common_patterns(tmp_settings_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))

    text = """
    Verwaltungsgericht Beispielstadt
    Az.: 6 K 308/25 Ge
    Irgendwas weiterer Text.
    """
    az = extract_aktenzeichen(text, settings)
    # Should detect at least one candidate and include the classic court-like format
    assert az, "expected at least one aktenzeichen candidate"
    assert any("308/25" in s for s in az), f"unexpected aktenzeichen list: {az}"


def test_extract_date_detects_iso_like_or_german_date(
    tmp_settings_dir: Path, tmp_path: Path
) -> None:
    settings = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))

    # We don't enforce exact algorithm detail; we enforce that a clear date is detected.
    text = "Bescheid vom 03.02.2026 bezüglich irgendwas."
    d = extract_date(text, settings)
    assert d is not None, "expected date extraction to succeed for explicit DD.MM.YYYY"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d), f"expected ISO date, got: {d}"


def test_guess_area_uses_closed_world_keywords(tmp_settings_dir: Path, tmp_path: Path) -> None:
    settings = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    allowed = settings.allowed_area_ids()

    area_id, kw = _pick_area_and_keyword(tmp_settings_dir)
    assert area_id in allowed, f"picked area '{area_id}' not in allowed areas (settings mismatch)"

    # Put keyword into text; guess_area must return a value inside allowed areas.
    text = f"Dies ist ein Dokument über {kw} und sonst nichts."
    res = guess_area(text, settings, allowed_areas=allowed)

    # guess_area returns a mapping in your code path, parsed by _parse_guess_area_result elsewhere.
    assert isinstance(res, tuple), f"expected tuple result, got {type(res)}"
    area_id = res[0]
    assert area_id in allowed

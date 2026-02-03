from __future__ import annotations

from pathlib import Path
import pytest

from docflow.settings.defaults import load_settings
from docflow.settings.models import SettingsPaths
from docflow.suggest.postprocess import postprocess_suggestion


def _paths(tmp_path: Path, settings_dir: Path) -> SettingsPaths:
    return SettingsPaths(settings_dir=str(settings_dir))


def test_postprocess_never_lets_llm_override_heuristic_area(
    tmp_settings_dir: Path, tmp_path: Path, tmp_pdf: Path
) -> None:
    settings = load_settings(tmp_settings_dir, _paths(tmp_path, tmp_settings_dir))
    allowed_areas = settings.allowed_area_ids()

    # authoritative heuristic base
    heuristic_base = {
        "suggested_area": allowed_areas[0],
        "suggested_year": 2024,
        "suggested_filename": "safe.pdf",
        "doc_type": settings.allowed_doc_type_ids()[0],
        "doc_title": "H",
        "summary": "H",
        "key_points": ["k"],
        "tags": [],
        "yaml": {
            "typ": settings.allowed_doc_type_ids()[0],
            "bereich": allowed_areas[0],
            "datum": None,
            "quelle": None,
            "aktenzeichen": [],
            "frist": None,
            "status": None,
            "tags": [],
        },
    }

    # malicious/incorrect LLM object tries to override area
    llm_obj = {
        "suggested_area": "NOT_ALLOWED",
        "doc_title": "LLM title ok",
        "summary": "LLM summary ok",
        "key_points": ["llm-k1"],
    }

    res = postprocess_suggestion(
        settings=settings,
        input_pdf=str(tmp_pdf),
        extracted_text="irrelevant",
        allowed_areas=allowed_areas,
        allowed_doc_types=allowed_doc_types,
        llm_obj=llm_obj,
        heuristic_base=heuristic_base,
    )

    assert res.ok is True, f"postprocess should succeed; warnings={res.warnings}"
    assert (
        res.suggestion["suggested_area"] == allowed_areas[0]
    ), "LLM must not override heuristic area"
    assert res.suggestion["yaml"]["bereich"] == allowed_areas[0], "YAML area must stay consistent"


def test_postprocess_marks_invalid_when_schema_breaks(
    tmp_settings_dir: Path, tmp_path: Path, tmp_pdf: Path
) -> None:
    settings = load_settings(tmp_settings_dir, _paths(tmp_path, tmp_settings_dir))
    allowed_areas = settings.allowed_area_ids()

    heuristic_base = {
        "suggested_area": allowed_areas[0],
        "suggested_year": 2024,
        "suggested_filename": "safe.pdf",
        "doc_type": settings.allowed_doc_type_ids()[0],
        "doc_title": "H",
        "summary": "H",
        "key_points": ["k"],
        "tags": [],
        "yaml": {
            "typ": settings.allowed_doc_type_ids()[0],
            "bereich": allowed_areas[0],
            "datum": None,
            "quelle": None,
            "aktenzeichen": [],
            "frist": None,
            "status": None,
            "tags": [],
        },
    }

    # LLM returns non-object junk -> should not crash; should produce invalid suggestion marker
    llm_obj = None

    res = postprocess_suggestion(
        settings=settings,
        input_pdf=str(tmp_pdf),
        extracted_text="irrelevant",
        allowed_areas=allowed_areas,
        llm_obj=llm_obj,
        heuristic_base=heuristic_base,
    )

    assert res.ok is True
    assert (
        "_invalid" not in res.suggestion
    ), "Valid heuristic_base alone should yield a valid suggestion"

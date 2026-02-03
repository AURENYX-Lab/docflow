from __future__ import annotations

import pytest

from docflow.core.schema import validate_suggestion_dict, validate_suggestion_against_settings


def _make_min_suggestion(
    *, input_pdf: str, area: str, year: int, filename: str, doc_type: str
) -> dict:
    return {
        "input_pdf": input_pdf,
        "suggested_area": area,
        "suggested_year": year,
        "suggested_filename": filename,
        "doc_type": doc_type,
        "doc_title": "t",
        "summary": "s",
        "key_points": ["k1"],
        "yaml": {
            "typ": doc_type,
            "bereich": area,
            "datum": None,
            "quelle": None,
            "aktenzeichen": [],
            "frist": None,
            "status": None,
            "tags": [],
            # zusätzliche YAML keys wären erlaubt (additionalProperties: True)
        },
    }


def test_suggestion_extra_fields_forbidden(tmp_pdf, tmp_settings_dir, tmp_path):
    from docflow.settings.defaults import load_settings
    from docflow.settings.models import SettingsPaths

    settings = load_settings(
        tmp_settings_dir,
        SettingsPaths(settings_dir=str(tmp_settings_dir)),
    )
    area = settings.allowed_area_ids()[0]
    doc_type = settings.allowed_doc_type_ids()[0]

    d = _make_min_suggestion(
        input_pdf=str(tmp_pdf), area=area, year=2024, filename="x.pdf", doc_type=doc_type
    )
    d["hacker_field"] = 123

    with pytest.raises(Exception) as e:
        _ = validate_suggestion_dict(d)

    # message je nach pydantic version: "extra fields not permitted" / "extra_forbidden"
    assert "extra" in str(e.value).lower()


def test_validate_suggestion_rejects_unknown_area(tmp_pdf, tmp_settings_dir, tmp_path):
    from docflow.settings.defaults import load_settings
    from docflow.settings.models import SettingsPaths

    settings = load_settings(
        tmp_settings_dir,
        SettingsPaths(settings_dir=str(tmp_settings_dir)),
    )
    doc_type = settings.allowed_doc_type_ids()[0]

    d = _make_min_suggestion(
        input_pdf=str(tmp_pdf), area="NOT_ALLOWED", year=2024, filename="x.pdf", doc_type=doc_type
    )
    sug = validate_suggestion_dict(d)

    with pytest.raises(ValueError) as e:
        validate_suggestion_against_settings(
            sug,
            settings=settings,
            allowed_area_ids=settings.allowed_area_ids(),
            allowed_doc_type_ids=settings.allowed_doc_type_ids(),
        )
    assert "allowed areas" in str(e.value).lower() or "not allowed" in str(e.value).lower()


def test_validate_suggestion_year_range_enforced(tmp_pdf, tmp_settings_dir, tmp_path):
    from docflow.settings.defaults import load_settings
    from docflow.settings.models import SettingsPaths

    settings = load_settings(
        tmp_settings_dir,
        SettingsPaths(settings_dir=str(tmp_settings_dir)),
    )
    area = settings.allowed_area_ids()[0]
    doc_type = settings.allowed_doc_type_ids()[0]

    d = _make_min_suggestion(
        input_pdf=str(tmp_pdf), area=area, year=1800, filename="x.pdf", doc_type=doc_type
    )
    sug = validate_suggestion_dict(d)

    with pytest.raises(ValueError) as e:
        validate_suggestion_against_settings(
            sug,
            settings=settings,
            allowed_area_ids=settings.allowed_area_ids(),
            allowed_doc_type_ids=settings.allowed_doc_type_ids(),
        )
    assert "year" in str(e.value).lower() and "range" in str(e.value).lower()


def test_validate_suggestion_filename_must_end_with_pdf(tmp_pdf, tmp_settings_dir, tmp_path):
    from docflow.settings.defaults import load_settings
    from docflow.settings.models import SettingsPaths

    settings = load_settings(
        tmp_settings_dir,
        SettingsPaths(settings_dir=str(tmp_settings_dir)),
    )
    area = settings.allowed_area_ids()[0]
    doc_type = settings.allowed_doc_type_ids()[0]

    d = _make_min_suggestion(
        input_pdf=str(tmp_pdf), area=area, year=2024, filename="x.txt", doc_type=doc_type
    )
    sug = validate_suggestion_dict(d)

    with pytest.raises(ValueError) as e:
        validate_suggestion_against_settings(
            sug,
            settings=settings,
            allowed_area_ids=settings.allowed_area_ids(),
            allowed_doc_type_ids=settings.allowed_doc_type_ids(),
        )
    assert ".pdf" in str(e.value).lower()

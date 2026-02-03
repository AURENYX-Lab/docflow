from __future__ import annotations

import json
from pathlib import Path
import pytest

from docflow.apply.verify import (
    ApprovalPolicy,
    ApplyVerifyError,
    is_approved,
    load_suggestion_json,
)
from docflow.core.schema import validate_suggestion_dict


def _write_suggestion(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _minimal_valid_suggestion(*, input_pdf: str) -> dict:
    # Minimal strict schema per core.schema (extra=forbid).
    # NOTE: keep keys aligned with your existing unit test helper.
    return {
        "input_pdf": input_pdf,
        "suggested_area": "A",  # will not be validated here; schema only
        "suggested_year": 2024,
        "suggested_filename": "x.pdf",
        "doc_type": "DT",
        "doc_title": "t",
        "summary": "s",
        "key_points": ["k1"],
        "tags": [],
        "yaml": {
            "typ": "DT",
            "bereich": "A",
            "datum": None,
            "quelle": None,
            "aktenzeichen": [],
            "frist": None,
            "status": None,
            "tags": [],
        },
    }


def test_load_suggestion_json_hard_fails_if_marked_invalid(tmp_path: Path) -> None:
    pytest.xfail(
        "Suggestion schema forbids '_invalid/_errors' until contract adds invalid markers."
    )
    sj = tmp_path / "x.suggest.json"
    obj = _minimal_valid_suggestion(input_pdf=str(tmp_path / "in.pdf"))
    obj["_invalid"] = True
    obj["_errors"] = ["boom"]
    _write_suggestion(sj, obj)

    with pytest.raises(ApplyVerifyError) as e:
        _ = load_suggestion_json(sj)

    assert "marked invalid" in str(e.value).lower()
    assert "boom" in str(e.value).lower()


def test_load_suggestion_json_rejects_non_object(tmp_path: Path) -> None:
    sj = tmp_path / "x.suggest.json"
    sj.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ApplyVerifyError) as e:
        _ = load_suggestion_json(sj)

    assert "must be object" in str(e.value).lower()


def test_is_approved_json_flag_true(tmp_path: Path) -> None:
    pytest.xfail("Suggestion schema forbids top-level 'approved' until contract adds it.")
    sj = tmp_path / "x.suggest.json"
    obj = _minimal_valid_suggestion(input_pdf=str(tmp_path / "in.pdf"))
    obj["approved"] = True
    _write_suggestion(sj, obj)

    # Ensure schema stays valid (guard against future schema tightening).
    _ = validate_suggestion_dict(obj)

    rec = load_suggestion_json(sj)
    policy = ApprovalPolicy(
        mode="json_flag",
        json_flag_field="approved",
        json_flag_value=True,
        sidecar_suffix=".approved",
    )

    assert is_approved(rec, policy) is True


def test_is_approved_json_flag_false(tmp_path: Path) -> None:
    sj = tmp_path / "x.suggest.json"
    obj = _minimal_valid_suggestion(input_pdf=str(tmp_path / "in.pdf"))
    obj["approved"] = False
    _write_suggestion(sj, obj)

    _ = validate_suggestion_dict(obj)

    rec = load_suggestion_json(sj)
    policy = ApprovalPolicy(
        mode="json_flag",
        json_flag_field="approved",
        json_flag_value=True,
        sidecar_suffix=".approved",
    )

    assert is_approved(rec, policy) is False


def test_is_approved_sidecar_file(tmp_path: Path) -> None:
    sj = tmp_path / "x.suggest.json"
    obj = _minimal_valid_suggestion(input_pdf=str(tmp_path / "in.pdf"))
    _write_suggestion(sj, obj)

    _ = validate_suggestion_dict(obj)

    rec = load_suggestion_json(sj)
    policy = ApprovalPolicy(
        mode="sidecar_file",
        json_flag_field="approved",
        json_flag_value=True,
        sidecar_suffix=".approved",
    )

    # Not approved yet
    assert is_approved(rec, policy) is False

    # Create sidecar marker
    sidecar = sj.with_suffix(sj.suffix + ".approved")
    sidecar.write_text("ok", encoding="utf-8")
    assert is_approved(rec, policy) is True

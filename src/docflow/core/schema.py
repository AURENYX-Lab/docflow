# docflow/src/docflow/core/schema.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from docflow.settings import Settings


# -----------------------
# JSON Schema (for prompt)
# -----------------------

DOCFLOW_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "input_pdf",
        "suggested_area",
        "suggested_year",
        "suggested_filename",
        "doc_type",
        "doc_title",
        "summary",
        "key_points",
        "yaml",
    ],
    "properties": {
        "input_pdf": {"type": "string"},
        "suggested_area": {"type": "string"},
        "suggested_year": {"type": "integer"},
        "suggested_filename": {"type": "string"},
        "doc_type": {"type": "string"},
        "doc_title": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "yaml": {
            "type": "object",
            # allow extra YAML keys for future expansion
            "additionalProperties": True,
            "required": [
                "typ",
                "bereich",
                "datum",
                "quelle",
                "aktenzeichen",
                "frist",
                "status",
                "tags",
            ],
            "properties": {
                "typ": {"type": ["string", "null"]},
                "bereich": {"type": ["string", "null"]},
                "datum": {"type": ["string", "null"]},
                "quelle": {"type": ["string", "null"]},
                "aktenzeichen": {"type": "array", "items": {"type": "string"}},
                "frist": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"]},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


def dumps_min(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# -----------------------
# Pydantic Models (truth)
# -----------------------


class YamlMeta(BaseModel):
    """
    YAML frontmatter-like metadata container.
    Allows extra keys so you can extend without breaking.
    """

    model_config = ConfigDict(extra="allow")

    typ: Optional[str] = None
    bereich: Optional[str] = None
    datum: Optional[str] = None
    quelle: Optional[str] = None
    aktenzeichen: List[str] = Field(default_factory=list)
    frist: Optional[str] = None
    status: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    """
    Strict top-level schema: no additional properties.
    """

    model_config = ConfigDict(extra="forbid")

    input_pdf: str
    suggested_area: str
    suggested_year: int
    suggested_filename: str
    doc_type: str
    doc_title: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    yaml: YamlMeta


def validate_suggestion_dict(obj: Dict[str, Any]) -> Suggestion:
    return Suggestion.model_validate(obj)


def validate_suggestion_against_settings(
    sug: Suggestion, *, allowed_area_ids: List[str], allowed_doc_type_ids: List[str]
) -> None:
    min_year = int(settings.heuristics.date_detection.min_year)
    max_year = int(settings.heuristics.date_detection.max_year)
    if sug.suggested_area not in set(allowed_area_ids):
        raise ValueError(f"suggested_area '{sug.suggested_area}' not in allowed areas")

    if sug.doc_type not in set(allowed_doc_type_ids):
        raise ValueError(f"doc_type '{sug.doc_type}' not in allowed doctypes")

    if sug.yaml.bereich and sug.yaml.bereich != sug.suggested_area:
        raise ValueError("suggested_area != yaml.bereich (inconsistent suggestion)")

    if sug.yaml.typ and sug.yaml.typ != sug.doc_type:
        raise ValueError("doc_type != yaml.typ (inconsistent suggestion)")

    if not (min_year <= int(sug.suggested_year) <= max_year):
        raise ValueError(f"suggested_year out of range: {sug.suggested_year}")

    if not sug.suggested_filename.lower().endswith(".pdf"):
        raise ValueError("suggested_filename must end with .pdf")

    if len(sug.key_points) > 25:
        raise ValueError("key_points too long (cap at 25)")

    if not sug.doc_type.strip():
        raise ValueError("doc_type must be non-empty")
    if (sug.yaml.typ or "") != (sug.doc_type or ""):
        raise ValueError("doc_type != yaml.typ (inconsistent suggestion)")

    if not sug.doc_title.strip():
        raise ValueError("doc_title must be non-empty")
    if not sug.summary.strip():
        raise ValueError("summary must be non-empty")

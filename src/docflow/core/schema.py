from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class YamlMeta(BaseModel):
    """
    YAML frontmatter-like metadata container.
    extra keys allowed (you may add more later without breaking schema).
    """

    model_config = ConfigDict(extra="allow")

    typ: Optional[str] = None
    bereich: Optional[str] = None
    datum: Optional[str] = None  # YYYY-MM-DD or null
    quelle: Optional[str] = None
    aktenzeichen: List[str] = Field(default_factory=list)
    frist: Optional[str] = None  # YYYY-MM-DD or null
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
    doc_title: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    yaml: YamlMeta


def validate_suggestion_dict(obj: Dict[str, Any]) -> Suggestion:
    return Suggestion.model_validate(obj)


def validate_suggestion_against_settings(sug: Suggestion, *, allowed_area_ids: List[str]) -> None:
    if sug.suggested_area not in set(allowed_area_ids):
        raise ValueError(f"suggested_area '{sug.suggested_area}' not in allowed areas")

    if not (1900 <= int(sug.suggested_year) <= 2100):
        raise ValueError(f"suggested_year out of range: {sug.suggested_year}")

    if not sug.suggested_filename.lower().endswith(".pdf"):
        raise ValueError("suggested_filename must end with .pdf")

    if len(sug.key_points) > 25:
        raise ValueError("key_points too long (cap at 25)")

    # minimal sanity: forbid empty title/summary
    if not sug.doc_title.strip():
        raise ValueError("doc_title must be non-empty")
    if not sug.summary.strip():
        raise ValueError("summary must be non-empty")

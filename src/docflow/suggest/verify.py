# docflow/src/docflow/suggest/verify.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from docflow.core.schema import (
    validate_suggestion_against_settings,
    validate_suggestion_dict,
)
from docflow.settings import Settings


class SuggestVerifyError(ValueError):
    pass


_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+\.pdf$")


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    errors: List[str]


def verify_suggestion(
    obj: Dict[str, Any],
    settings: Settings,
    *,
    allowed_areas: Sequence[str],
    allowed_doc_types: Sequence[str],
    min_year: int = 1990,
    max_year: int = 2100,
) -> VerifyReport:
    errors: List[str] = []

    try:
        s = validate_suggestion_dict(obj)
    except Exception as e:
        return VerifyReport(
            ok=False,
            errors=[f"Schema validation failed: {type(e).__name__}: {e}"],
        )

    # settings-level invariants (area/doctypes + yaml consistency)
    try:
        validate_suggestion_against_settings(
            s,
            settings=settings,
            allowed_area_ids=list(allowed_areas),
            allowed_doc_type_ids=list(allowed_doc_types),
        )
    except Exception as e:
        errors.append(f"Settings validation failed: {type(e).__name__}: {e}")

    if s.suggested_area not in allowed_areas:
        errors.append(f"suggested_area not allowed: {s.suggested_area}")

    if not (min_year <= int(s.suggested_year) <= max_year):
        errors.append(f"suggested_year out of range: {s.suggested_year}")

    return VerifyReport(ok=not errors, errors=errors)

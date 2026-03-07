# docflow/src/docflow/apply/verify.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from docflow.core.schema import validate_suggestion_dict
from docflow.settings import Settings


class ApplyVerifyError(ValueError):
    pass


@dataclass(frozen=True)
class ApprovalPolicy:
    mode: str
    json_flag_field: str
    json_flag_value: bool
    sidecar_suffix: str

    @staticmethod
    def from_settings(settings: Settings) -> "ApprovalPolicy":
        a = settings.pipeline.apply.approval
        mode = a.mode
        if mode not in ("json_flag", "sidecar_file"):
            raise ApplyVerifyError(
                "apply.approval.mode must be 'json_flag' or 'sidecar_file'"
            )

        if not a.json_flag_field.strip():
            raise ApplyVerifyError("apply.approval.json_flag_field must be non-empty")
        if not isinstance(a.json_flag_value, bool):
            raise ApplyVerifyError("apply.approval.json_flag_value must be boolean")
        if not a.sidecar_suffix.strip():
            raise ApplyVerifyError("apply.approval.sidecar_suffix must be non-empty")

        return ApprovalPolicy(
            mode=mode,
            json_flag_field=a.json_flag_field.strip(),
            json_flag_value=bool(a.json_flag_value),
            sidecar_suffix=a.sidecar_suffix,
        )


@dataclass(frozen=True)
class SuggestionRecord:
    suggestion_path: Path
    data: Dict[str, Any]


def load_suggestion_json(path: Path) -> SuggestionRecord:
    if not path.exists() or not path.is_file():
        raise ApplyVerifyError(f"Suggestion JSON not found: {path}")

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ApplyVerifyError(
            f"Failed to parse JSON {path.name}: {type(e).__name__}: {e}"
        ) from e

    if not isinstance(obj, dict):
        raise ApplyVerifyError(f"Suggestion JSON must be object: {path.name}")

    suggestion = validate_suggestion_dict(obj)

    if suggestion.invalid:
        errs = getattr(suggestion, "errors", []) or []
        preview = ", ".join(str(x) for x in errs[:3])  # bounded + deterministic
        suffix = f" errors=[{preview}]" if preview else ""
        raise ApplyVerifyError(f"Suggestion marked invalid: {path.name}{suffix}")

    return SuggestionRecord(suggestion_path=path, data=obj)


def is_approved(rec: SuggestionRecord, policy: "ApprovalPolicy") -> bool:
    if policy.mode == "json_flag":
        val = rec.data.get(policy.json_flag_field)
        return val is policy.json_flag_value

    if policy.mode == "sidecar_file":
        sidecar = rec.suggestion_path.with_suffix(
            rec.suggestion_path.suffix + policy.sidecar_suffix
        )
        return sidecar.exists()

    raise ApplyVerifyError(f"Unknown approval mode: {policy.mode}")


def get_input_pdf_path(rec: SuggestionRecord) -> Path:
    p = rec.data.get("input_pdf")
    if not isinstance(p, str) or not p.strip():
        raise ApplyVerifyError("Suggestion missing input_pdf")
    return Path(p).expanduser().resolve()

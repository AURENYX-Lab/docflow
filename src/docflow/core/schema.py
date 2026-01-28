from __future__ import annotations
from typing import Any
import json

TOP_KEYS = [
    "input_pdf",
    "suggested_area",
    "suggested_year",
    "suggested_filename",
    "doc_title",
    "summary",
    "key_points",
    "yaml",
]
YAML_KEYS = ["typ", "bereich", "datum", "quelle", "aktenzeichen", "frist", "status", "tags"]


def validate_doc(obj: dict[str, Any]) -> None:
    # additionalProperties False for top-level
    extra = set(obj.keys()) - set(TOP_KEYS)
    if extra:
        raise ValueError(f"Top-level has extra keys not allowed: {sorted(extra)}")

    missing = [k for k in TOP_KEYS if k not in obj]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")

    if not isinstance(obj["suggested_year"], int):
        raise ValueError("suggested_year must be integer")

    if not isinstance(obj["key_points"], list) or not all(
        isinstance(x, str) for x in obj["key_points"]
    ):
        raise ValueError("key_points must be array of strings")

    y = obj["yaml"]
    if not isinstance(y, dict):
        raise ValueError("yaml must be object")

    missing_y = [k for k in YAML_KEYS if k not in y]
    if missing_y:
        raise ValueError(f"yaml missing required keys: {missing_y}")

    if not isinstance(y["aktenzeichen"], list) or not all(
        isinstance(x, str) for x in y["aktenzeichen"]
    ):
        raise ValueError("yaml.aktenzeichen must be array of strings")
    if not isinstance(y["tags"], list) or not all(isinstance(x, str) for x in y["tags"]):
        raise ValueError("yaml.tags must be array of strings")


def dumps_min(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

# docflow/src/docflow/suggest/jsonfix.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple


class JsonFixError(ValueError):
    pass


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _find_balanced_object(s: str) -> Optional[str]:
    """
    Extract first balanced {...} object. Deterministic and safe.
    """
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue
        else:
            if ch == '"':
                in_str = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def _repair_common_json(s: str) -> str:
    """
    Minimal, conservative repairs:
    - remove trailing commas
    - replace smart quotes (rare)
    - remove leading/trailing junk outside object
    """
    s = (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    # trailing commas in objects/arrays
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # remove BOM
    s = s.lstrip("\ufeff").strip()
    return s


@dataclass(frozen=True)
class JsonParseResult:
    ok: bool
    obj: Optional[Any]
    raw_json: str
    error: Optional[str] = None


def extract_and_parse_json(text: str) -> JsonParseResult:
    """
    Returns first JSON object found and parsed.
    Never executes code. Only json.loads after minimal repairs.
    """
    t = (text or "").strip()

    m = _JSON_BLOCK_RE.search(t)
    if m:
        candidate = m.group(1)
    else:
        candidate = _find_balanced_object(t) or ""

    candidate = _repair_common_json(candidate)

    if not candidate:
        return JsonParseResult(ok=False, obj=None, raw_json="", error="No JSON object found")

    try:
        obj = json.loads(candidate)
        return JsonParseResult(ok=True, obj=obj, raw_json=candidate)
    except Exception as e1:
        # second try: attempt to isolate object again after stripping
        candidate2 = _find_balanced_object(candidate) or candidate
        candidate2 = _repair_common_json(candidate2)
        try:
            obj = json.loads(candidate2)
            return JsonParseResult(ok=True, obj=obj, raw_json=candidate2)
        except Exception as e2:
            return JsonParseResult(
                ok=False, obj=None, raw_json=candidate2, error=f"{type(e2).__name__}: {e2}"
            )

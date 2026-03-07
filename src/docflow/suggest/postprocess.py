# docflow/src/docflow/suggest/postprocess.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, cast

from docflow.core.heuristics import (
    extract_aktenzeichen,
    extract_date,
    frist_from_text,
    guess_area,
    guess_doc_typ,
    guess_source,
)
from docflow.core.naming import build_suggested_filename

if TYPE_CHECKING:
    from docflow.settings import Settings


ALLOWED_YAML_EXTRAS = {
    "_llm_date_hint",
    "_llm_source_hint",
    "_llm_notes",
    "_llm_confidence",
}


def _heuristic_base_from_extraction(
    *,
    settings: Settings,
    extracted_text: str,
    allowed_areas: Sequence[str],
    allowed_doc_types: Sequence[str],
) -> Dict[str, Any]:
    """
    Deterministic baseline for human review when LLM is off/unavailable.
    Must not invent non-closed-world values for doc_type/area decisions.
    Heuristic facts still remain the truth in postprocess_suggestion().
    """
    h_date = extract_date(extracted_text, settings)
    ga_res = guess_area(extracted_text, settings, allowed_areas=allowed_areas)
    h_area, h_tags = _parse_guess_area_result(ga_res)
    h_src = guess_source(extracted_text, settings)

    _dt = guess_doc_typ(extracted_text, settings)
    h_typ = _as_str(_dt[0]) if isinstance(_dt, tuple) and len(_dt) >= 1 else None

    h_az = extract_aktenzeichen(extracted_text, settings)
    h_frist = frist_from_text(extracted_text, settings, base_date=h_date)

    y = h_date[:10] if h_date else "undatiert"
    area = h_area or (allowed_areas[0] if allowed_areas else "UNSORTIERT")
    src = h_src or "quelle"

    # doc_type here is only used for text fields (title/short_desc). decision is still in postprocess.
    typ = (
        (h_typ or (allowed_doc_types[0] if allowed_doc_types else "DOKUMENT"))
        .strip()
        .upper()
    )

    doc_title = f"{typ} – {src} – {y}"

    summary_parts: List[str] = [
        "Automatisch erzeugte Suggestion (ohne LLM).",
        f"Bereich: {area}.",
    ]
    if h_date:
        summary_parts.append(f"Datum: {h_date}.")
    if h_az:
        summary_parts.append(f"Aktenzeichen: {h_az[0]}.")
    if h_frist:
        summary_parts.append(f"Frist: {h_frist}.")
    summary = " ".join(summary_parts)

    key_points: List[str] = []
    if h_date:
        key_points.append(f"Datum erkannt: {h_date}")
    if h_az:
        key_points.append(f"Aktenzeichen erkannt: {', '.join(h_az[:3])}")
    if h_frist:
        key_points.append(f"Frist abgeleitet: {h_frist}")
    key_points.append(f"Bereich-Heuristik: {area}")
    key_points.append(f"Quelle-Heuristik: {src}")

    return {
        "doc_title": doc_title,
        "summary": summary,
        "key_points": key_points[:8],
        "short_desc": typ,
        "status": "offen",
        "source": src,
        "area": area,
        "tags": h_tags[:6],
        "datum": h_date,
        "typ": typ,
        "aktenzeichen": h_az,
        "frist": h_frist,
    }


def _as_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x).strip()
    return s if s else None


def _as_list_str(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        out: List[str] = []
        for v in x:
            s = _as_str(v)
            if s:
                out.append(s)
        return out
    s = _as_str(x)
    return [s] if s else []


def _uniq_keep_order(xs: Sequence[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _norm_tag(s: str) -> str:
    s = s.strip().lower()
    s = s.replace(" ", "_")
    return s


def _parse_guess_area_result(res: Any) -> Tuple[Optional[str], List[str]]:
    """
    Backward compatible:
    - some versions return (area, tags)
    - some return just area
    - some may return None
    """
    if res is None:
        return None, []
    if isinstance(res, tuple) and len(res) == 2:
        area = _as_str(res[0])
        tags = _as_list_str(res[1])
        return area, tags
    # single value
    return _as_str(res), []


def _year_from_iso(iso_date: Optional[str]) -> Optional[int]:
    if not iso_date:
        return None
    if len(iso_date) < 4:
        return None
    y = iso_date[:4]
    if not y.isdigit():
        return None
    return int(y)


@dataclass(frozen=True)
class PostprocessResult:
    suggestion: Dict[str, Any]
    warnings: List[str]

    @property
    def ok(self) -> bool:
        return not bool(self.suggestion.get("_invalid"))


def postprocess_suggestion(
    *,
    settings: Settings,
    input_pdf: str,
    extracted_text: str,
    allowed_areas: Sequence[str],
    allowed_doc_types: Sequence[str],
    llm_obj: Optional[Dict[str, Any]],
    heuristic_base: Dict[str, Any],
) -> PostprocessResult:
    """
    Deterministic merge with Closed World enforcement:

    - Heuristics are primary truth for: area/date/year/source/type/aktenzeichen/frist
      (LLM may only fill when heuristic is missing; never override a valid heuristic)
    - LLM may enrich: doc_title/summary/key_points/status/short_desc/tags/yaml extras
    - output is schema-stable, reproducible, and warnings explain fallbacks
    """
    warnings: List[str] = []

    # If caller didn't provide a heuristic_base, build a deterministic one.
    if not heuristic_base:
        heuristic_base = _heuristic_base_from_extraction(
            settings=settings,
            extracted_text=extracted_text,
            allowed_areas=allowed_areas,
            allowed_doc_types=allowed_doc_types,
        )

    # --- Authoritative heuristic baseline ---
    h_date = extract_date(extracted_text, settings)
    ga_res = guess_area(extracted_text, settings, allowed_areas=allowed_areas)
    h_area, h_tags = _parse_guess_area_result(ga_res)

    h_src = guess_source(extracted_text, settings)
    _dt = guess_doc_typ(extracted_text, settings)

    h_typ: Optional[str] = None
    dt_tags: List[str] = []
    dt_is_hard: bool = False
    dt_implied_area: Optional[str] = None

    if isinstance(_dt, tuple) and len(_dt) >= 1:
        h_typ = _as_str(_dt[0])

        # Recommended style: (id, hit, hits)
        if len(_dt) >= 2 and _dt[1] is not None:
            hit = _dt[1]
            dt_is_hard = bool(getattr(hit, "hard", False))
            dt_implied_area = _as_str(getattr(hit, "implied_area", None)) or _as_str(
                getattr(hit, "likely_area", None)
            )
            # optional if you add tags to DocTypeHit later:
            dt_tags = _as_list_str(getattr(hit, "tags", None))

        # Legacy style: (id, tags, debug)
        elif len(_dt) >= 2:
            dt_tags = _as_list_str(_dt[1])

    h_az = extract_aktenzeichen(extracted_text, settings)
    h_frist = frist_from_text(extracted_text, settings, base_date=h_date)

    # --- Start from LLM object (optional) ---
    obj: Dict[str, Any] = dict(llm_obj or {})

    # --- Human-visible enriched fields (LLM allowed, with heuristic_base fallback) ---
    doc_title = (
        _as_str(obj.get("doc_title"))
        or _as_str(heuristic_base.get("doc_title"))
        or "Dokument"
    )

    summary = (
        _as_str(obj.get("summary")) or _as_str(heuristic_base.get("summary")) or "—"
    )

    key_points = _as_list_str(obj.get("key_points"))
    if not key_points:
        key_points = _as_list_str(heuristic_base.get("key_points"))
    key_points = [kp for kp in key_points if kp][:8]

    # --- YAML block from LLM (optional) ---
    y = obj.get("yaml")
    if not isinstance(y, dict):
        y = {}
        warnings.append("LLM yaml missing/invalid; rebuilt from heuristics")
    y = cast(Dict[str, Any], y)

    # status: allow LLM -> heuristic_base -> default
    status = (
        _as_str(y.get("status"))
        or _as_str(obj.get("status"))
        or _as_str(heuristic_base.get("status"))
        or "offen"
    )

    # --- Area selection (Phase-3 rule, EXACT; Closed World) ---
    # LLM area is ignored for decision, but can be used for a warning.
    llm_area = _as_str(obj.get("suggested_area")) or _as_str(y.get("bereich"))

    area: Optional[str] = None

    # 1) Hard DocType with implied_area overrides area guess
    if dt_is_hard and dt_implied_area:
        if dt_implied_area in allowed_areas:
            area = dt_implied_area
        else:
            warnings.append("DocType implied_area not allowed; ignoring implied_area")

    # 2) else take heuristic area guess (only if allowed)
    if area is None:
        if h_area in allowed_areas:
            area = h_area

    # 3) else deterministic fallback: allowed_areas[0]
    if area is None:
        area = allowed_areas[0] if allowed_areas else "UNSORTIERT"
        warnings.append("No valid area guess; using allowed_areas[0] fallback")

    # Optional warning: LLM disagrees (for human review), but does not affect decision
    if llm_area and llm_area != area:
        warnings.append(f"LLM suggested_area '{llm_area}' ignored; using '{area}'")

    # --- Date / year selection (STRICT: heuristic truth, LLM = hint only) ---
    llm_date = _as_str(y.get("datum")) or _as_str(obj.get("datum"))

    iso_date = h_date  # heuristic only
    year = _year_from_iso(iso_date)

    # ensure year is always an int within allowed range (contract-stable)
    min_year = int(settings.heuristics.date_detection.min_year)
    max_year = int(settings.heuristics.date_detection.max_year)

    if iso_date is None:
        year = min_year
        if llm_date:
            warnings.append(
                f"LLM suggested date '{llm_date}' ignored; heuristic date missing"
            )
        else:
            warnings.append(
                f"No date detected; using year={min_year} (min_year) and datum=None"
            )
    else:
        # if date exists but year parsing failed or out of bounds, clamp deterministically
        if year is None:
            warnings.append(
                f"Date detected ('{iso_date}') but year parse failed; using year={min_year}"
            )
            year = min_year
        elif year < min_year:
            warnings.append(f"Year {year} < min_year {min_year}; clamping to min_year")
            year = min_year
        elif year > max_year:
            warnings.append(f"Year {year} > max_year {max_year}; clamping to max_year")
            year = max_year

    # --- Source (heuristic primary; LLM only if heuristic missing) ---
    llm_source = _as_str(y.get("quelle")) or _as_str(obj.get("source"))
    base_source = _as_str(heuristic_base.get("source"))

    source = h_src or llm_source or base_source or "quelle"

    # --- Short description (LLM allowed; else heuristic_base; else doc_title) ---
    short_desc = (
        _as_str(obj.get("short_desc"))
        or _as_str(heuristic_base.get("short_desc"))
        or doc_title
    )

    suggested_filename = build_suggested_filename(
        settings=settings,
        iso_date=iso_date,
        short_desc=short_desc,
        source=source,
        status=status,
    )

    # --- Aktenzeichen merge (heuristic + LLM yaml + LLM top-level) ---
    llm_az = _as_list_str(y.get("aktenzeichen")) + _as_list_str(obj.get("aktenzeichen"))
    az = _uniq_keep_order([*h_az, *llm_az])

    # --- Tags merge (heuristics + LLM), fenced ---
    llm_tags_raw = _as_list_str(y.get("tags")) + _as_list_str(obj.get("tags"))
    llm_tags = [_norm_tag(t) for t in llm_tags_raw if _as_str(t)]

    base_tags_raw = [*h_tags, *dt_tags]
    base_tags = [_norm_tag(t) for t in base_tags_raw if _as_str(t)]

    tags = _uniq_keep_order([*base_tags, *llm_tags])
    tags = [t for t in tags if 2 <= len(t) <= 32][:12]

    # --- Frist / Typ (heuristic primary; LLM allowed only if heuristic missing) ---
    llm_frist = _as_str(y.get("frist")) or _as_str(obj.get("frist"))
    frist = h_frist or llm_frist

    llm_doc_type = _as_str(obj.get("doc_type"))  # optional (LLM)
    llm_typ = _as_str(y.get("typ")) or _as_str(obj.get("typ"))
    doc_type = h_typ or llm_doc_type or llm_typ

    # closed-world fallback (deterministic)
    if not doc_type:
        if allowed_doc_types:
            doc_type = str(allowed_doc_types[0])
            warnings.append(
                f"No doc_type detected; using doc_type={doc_type} (first allowed)"
            )
        else:
            # should never happen if settings are valid, but don't crash
            doc_type = "DOKUMENT"

    # normalize doc_type (your IDs are uppercase)
    doc_type = str(doc_type).strip().upper()
    allowed_dt_norm = {str(x).strip().upper() for x in allowed_doc_types}

    # enforce Closed World right here (do NOT output illegal doc_type)
    if allowed_dt_norm and doc_type not in allowed_dt_norm:
        fallback = next(iter(allowed_dt_norm))  # oder allowed_doc_types[0] normalisiert
        warnings.append(f"doc_type '{doc_type}' not allowed; using '{fallback}'")
        doc_type = fallback

    # --- Build final YAML first (so we can add hints cleanly) ---
    final_yaml: Dict[str, Any] = {
        "typ": doc_type,
        "bereich": str(area),
        "datum": iso_date,
        "quelle": source,
        "aktenzeichen": az,
        "frist": frist,
        "status": status,
        "tags": tags,
    }

    # save LLM date hint ONLY if heuristic date missing
    if llm_date and iso_date is None:
        final_yaml["_llm_date_hint"] = llm_date

    # --- Build final object (schema-stable) ---
    final: Dict[str, Any] = {
        "input_pdf": str(input_pdf),
        "suggested_area": str(area),
        "suggested_year": int(year),
        "suggested_filename": str(suggested_filename),
        "doc_type": doc_type,
        "doc_title": str(doc_title),
        "summary": str(summary),
        "key_points": key_points,
        "yaml": final_yaml,
    }

    # Keep ONLY whitelisted extra yaml keys from LLM (governance; no hidden decisions)
    for k, v in y.items():
        if k in ALLOWED_YAML_EXTRAS and k not in final_yaml:
            final_yaml[k] = v

    return PostprocessResult(suggestion=final, warnings=warnings)

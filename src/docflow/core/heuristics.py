# docflow/src/docflow/core/heuristics.py
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date as _date
from typing import Any, Dict, List, Optional, Sequence, Tuple
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docflow.settings import Settings


_UMLAUT_NORM = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def _norm(s: str) -> str:
    s = (s or "").translate(_UMLAUT_NORM).lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------
# Source / Quelle extraction (settings-driven, closed world)
# ---------------------------

_SAFE_SRC_RE = re.compile(r"[^a-z0-9_-]+")


def _safe_source_id(s: str) -> str:
    s = _norm(s)
    s = s.replace(" ", "_")
    s = _SAFE_SRC_RE.sub("", s)
    s = s.strip("_-")
    # deterministisch begrenzen (filename-safe)
    return s[:32] if s else ""


@dataclass(frozen=True)
class SourceHit:
    source: str
    score: int
    matched: List[str]


def _score_keyword_hit(norm_text: str, kw: str) -> int:
    """
    Deterministic scoring:
    - phrase (contains space) => +3 if substring hit
    - token => +2 if boundary-ish hit (avoid matching inside long words)
    """
    nkw = _norm(kw)
    if not nkw:
        return 0

    if " " in nkw:
        return 3 if nkw in norm_text else 0

    # boundary-ish token match
    if re.search(rf"(?<![a-z0-9]){re.escape(nkw)}(?![a-z0-9])", norm_text):
        return 2
    return 0


def guess_source(text: str, settings: Settings) -> Optional[str]:
    """
    Guess 'source' deterministically using settings.heuristics.source_guess.rules.
    Returns a filename-safe short id or None.
    """
    best, _hit, _all = guess_source_debug(text, settings)
    return best


def guess_source_debug(
    text: str, settings: Settings
) -> Tuple[Optional[str], Optional[SourceHit], List[SourceHit]]:
    """
    Same as guess_source, but returns debug hits.
    Returns: (best_source_id, best_hit, all_hits)
    """
    t = _norm((text or "").replace("\x00", " "))

    # Pydantic runtime truth
    rules = []
    try:
        rules = list(settings.heuristics.source_guess.rules)
    except Exception:
        rules = []

    hits: List[SourceHit] = []

    for r in rules:
        try:
            src_raw = str(r.source)
            kws = list(r.keywords)
        except Exception:
            # if rule shape is unexpected, ignore deterministically
            continue

        src = _safe_source_id(src_raw)
        if not src or not kws:
            continue

        matched: List[str] = []
        score = 0

        for kw in kws:
            if not isinstance(kw, str) or not kw.strip():
                continue
            inc = _score_keyword_hit(t, kw)
            if inc > 0:
                matched.append(kw)
                score += inc

        if score > 0:
            hits.append(SourceHit(source=src, score=score, matched=matched[:25]))

    if not hits:
        return None, None, []

    # Deterministic tie-break:
    # 1) score desc
    # 2) number of matches desc
    # 3) source id asc
    hits.sort(key=lambda h: (-h.score, -len(h.matched), h.source))
    best = hits[0]
    return best.source, best, hits


# ---------------------------
# Date extraction
# ---------------------------

RE_ISO = re.compile(r"\b((?:19|20)\d{2})-([01]\d)-([0-3]\d)\b")
RE_DMY = re.compile(r"\b([0-3]?\d)[\.\-/ ]+([01]?\d)[\.\-/ ]+((?:19|20)?\d{2})\b", re.I)
RE_MONTHNAME = re.compile(
    r"\b([0-3]?\d)\.\s*(januar|februar|maerz|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+((?:19|20)\d{2})\b",
    re.I,
)

_MONTHS = {
    "januar": 1,
    "februar": 2,
    "maerz": 3,
    "märz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


def _norm_year(y: str) -> int:
    y = y.strip()
    if len(y) == 4:
        return int(y)
    yy = int(y)
    return 1900 + yy if yy >= 70 else 2000 + yy


def _valid_date(y: int, m: int, d: int, *, min_y: int, max_y: int) -> Optional[str]:
    if y < min_y or y > max_y:
        return None
    try:
        return _date(y, m, d).isoformat()
    except Exception:
        return None


def extract_date(text: str, settings: Settings) -> Optional[str]:
    # Pydantic runtime truth (no dict access)
    min_y = int(settings.heuristics.date_detection.min_year)
    max_y = int(settings.heuristics.date_detection.max_year)

    t = (text or "").replace("\x00", " ")
    m = RE_ISO.search(t)
    if m:
        iso = _valid_date(
            int(m.group(1)), int(m.group(2)), int(m.group(3)), min_y=min_y, max_y=max_y
        )
        if iso:
            return iso

    for m in RE_DMY.finditer(t):
        iso = _valid_date(
            _norm_year(m.group(3)), int(m.group(2)), int(m.group(1)), min_y=min_y, max_y=max_y
        )
        if iso:
            return iso

    m = RE_MONTHNAME.search(t)
    if m:
        d = int(m.group(1))
        mon = _MONTHS[m.group(2).lower()]
        y = int(m.group(3))
        return _valid_date(y, mon, d, min_y=min_y, max_y=max_y)

    return None


def add_one_month(iso_date: str) -> Optional[str]:
    try:
        y, m, d = map(int, iso_date.split("-"))
        nm = m + 1
        ny = y + (nm - 1) // 12
        nm = ((nm - 1) % 12) + 1
        last = calendar.monthrange(ny, nm)[1]
        nd = min(d, last)
        return _date(ny, nm, nd).isoformat()
    except Exception:
        return None


# ---------------------------
# Aktenzeichen extraction
# ---------------------------

RE_AZ_LABEL = re.compile(
    r"\b(?:Az\.?|Aktenzeichen|Gz\.?|Gesch\.?-?\s*Z(?:eichen)?|Geschäftszeichen|Zeichen)\s*[:\-]?\s*"
    r"([A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9 .\-\/]{3,80})",
    re.I,
)

RE_COURT = re.compile(r"\b\d{1,3}\s*[A-Z]{1,3}\s*\d{1,6}\/\d{2,4}\b")


def extract_aktenzeichen(text: str, settings: Settings) -> List[str]:
    min_len = int(settings.heuristics.aktenzeichen.min_length)
    ignore_numeric_only = bool(settings.heuristics.aktenzeichen.ignore_numeric_only)

    t = (text or "").replace("\x00", " ").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)

    cands: List[str] = []

    for m in RE_AZ_LABEL.finditer(t):
        s = m.group(1).strip()
        s = re.split(r"\s{2,}|\n", s, 1)[0].strip()
        s = re.sub(r"\s+", " ", s).strip(".,;")
        if len(s) >= min_len:
            cands.append(s)

    for m in RE_COURT.finditer(t):
        s = re.sub(r"\s+", " ", m.group(0)).strip(".,;")
        if len(s) >= min_len:
            cands.append(s)

    out: List[str] = []
    seen = set()
    for s in cands:
        if not re.search(r"\d", s):
            continue
        if ignore_numeric_only and re.fullmatch(r"[0-9][0-9 \-()/]{6,}", s):
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ---------------------------
# Frist extraction
# ---------------------------


def frist_from_text(text: str, settings: Settings, *, base_date: Optional[str]) -> Optional[str]:
    if not base_date:
        return None

    t = _norm(text)
    triggers = list(settings.heuristics.frist.one_month_triggers)

    for pat in triggers:
        try:
            if re.search(pat, t, flags=re.I):
                return add_one_month(base_date)
        except re.error:
            if _norm(pat) in t:
                return add_one_month(base_date)

    return None


# ---------------------------
# Area classification (settings-driven, closed world)
# ---------------------------


@dataclass(frozen=True)
class AreaHit:
    area_id: str
    priority: int
    hard: bool
    score: int
    matched: List[str]
    tags: List[str]


def guess_area(
    text: str,
    settings: Settings,
    *,
    allowed_areas: Sequence[str],
) -> Tuple[Optional[str], List[str], List[AreaHit]]:
    """
    Settings-driven classifier:
    - Closed-world areas from categories.yaml (settings.categories.areas)
    - Uses keyword hits with scoring
    - Hard categories override
    - 08_KORRESPONDENZ is never chosen if any other area also hits
    Returns: (best_area_id, tags, debug_hits)
    """
    t = _norm(text)

    hits: List[AreaHit] = []
    for a in settings.categories.areas:
        area_id = str(a.id)
        if allowed_areas and area_id not in allowed_areas:
            continue

        priority = int(a.priority)
        hard = bool(a.hard)
        keywords = list(a.keywords)
        tags = list(a.tags)

        matched = [kw for kw in keywords if _norm(kw) in t]
        if not matched:
            continue

        score = len(matched) + sum(1 for kw in matched if len(kw) >= 10)

        hits.append(
            AreaHit(
                area_id=area_id,
                priority=priority,
                hard=hard,
                score=score,
                matched=matched[:25],
                tags=tags[:8],
            )
        )

    if not hits:
        return None, [], []

    hard_hits = [h for h in hits if h.hard]
    if hard_hits:
        hard_hits.sort(key=lambda h: (h.priority, -h.score, h.area_id))
        best = hard_hits[0]
        return best.area_id, best.tags[:3], hits

    hits.sort(key=lambda h: (h.priority, -h.score, h.area_id))

    if hits[0].area_id == "08_KORRESPONDENZ" and any(h.area_id != "08_KORRESPONDENZ" for h in hits):
        best_non = next(h for h in hits if h.area_id != "08_KORRESPONDENZ")
        return best_non.area_id, best_non.tags[:3], hits

    best = hits[0]
    return best.area_id, best.tags[:3], hits


# ---------------------------
# DocType classification (settings-driven, closed world)
# ---------------------------


@dataclass(frozen=True)
class DocTypeHit:
    doc_type: str
    priority: int
    hard: bool
    score: int
    matched: List[str]
    implied_area: Optional[str]


def guess_doc_typ(
    text: str, settings: Settings
) -> Tuple[Optional[str], Optional[DocTypeHit], List[DocTypeHit]]:
    """
    Closed-world DocType matching:
    - matches keywords against normalized text
    - hard doctypes override soft doctypes
    - deterministic tie-breakers: (priority asc, score desc, id asc)
    Returns: (best_doctype_id, best_hit, all_hits)
    """
    t = _norm(text)

    hits: List[DocTypeHit] = []
    for dt in settings.doctypes.types:
        dt_id = str(dt.id)
        priority = int(dt.priority)
        hard = bool(dt.hard)
        kws = list(dt.keywords)

        matched = [kw for kw in kws if _norm(kw) in t]
        if not matched:
            continue

        score = len(matched) + sum(1 for kw in matched if len(kw) >= 10)

        implied_area = None
        if dt.implies is not None and getattr(dt.implies, "likely_area", None):
            implied_area = str(dt.implies.likely_area)

        hits.append(
            DocTypeHit(
                doc_type=dt_id,
                priority=priority,
                hard=hard,
                score=score,
                matched=matched[:25],
                implied_area=implied_area,
            )
        )

    if not hits:
        return None, None, []

    hard_hits = [h for h in hits if h.hard]
    if hard_hits:
        hard_hits.sort(key=lambda h: (h.priority, -h.score, h.doc_type))
        best = hard_hits[0]
        return best.doc_type, best, hits

    hits.sort(key=lambda h: (h.priority, -h.score, h.doc_type))
    # If KORRESPONDENZ hits but anything else hits too, prefer non-KORRESPONDENZ
    if any(h.doc_type != "KORRESPONDENZ" for h in hits):
        hits = [h for h in hits if h.doc_type != "KORRESPONDENZ"] + [
            h for h in hits if h.doc_type == "KORRESPONDENZ"
        ]

    best = hits[0]
    return best.doc_type, best, hits

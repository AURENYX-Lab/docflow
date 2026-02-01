from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
import calendar
from typing import Any, Dict, List, Optional, Tuple

from src.docflow.settings import Settings


_UMLAUT_NORM = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def _norm(s: str) -> str:
    s = (s or "").translate(_UMLAUT_NORM).lower()
    s = re.sub(r"\s+", " ", s)
    return s


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
    cfg = settings.heuristics.get("date_detection", {})
    min_y = int(cfg["min_year"])
    max_y = int(cfg["max_year"])

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
    cfg = settings.heuristics.get("aktenzeichen", {})
    min_len = int(cfg["min_length"])
    ignore_numeric_only = bool(cfg["ignore_numeric_only"])

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
# Area classification (settings-driven)
# ---------------------------


@dataclass(frozen=True)
class AreaHit:
    area_id: str
    priority: int
    hard: bool
    score: int
    matched: List[str]
    tags: List[str]


def guess_area(text: str, settings: Settings) -> Tuple[Optional[str], List[str], List[AreaHit]]:
    """
    Settings-driven classifier:
    - Closed-world areas from categories.yaml
    - Uses keyword hits with scoring
    - Hard categories (e.g. 05_RECHT_BEHOERDEN) override
    - 08_KORRESPONDENZ is *never* chosen if any other area also hits
    Returns: (best_area_id, tags, debug_hits)
    """
    t = _norm(text)
    areas = settings.categories["areas"]

    hits: List[AreaHit] = []
    for a in areas:
        area_id = str(a["id"])
        priority = int(a["priority"])
        hard = bool(a["hard"])
        keywords = a["keywords"]
        tags = a["tags"]

        matched = [kw for kw in keywords if _norm(kw) in t]
        if not matched:
            continue

        # score: count hits + small bonus for longer keywords (reduces noise)
        score = len(matched) + sum(1 for kw in matched if len(kw) >= 10)

        hits.append(
            AreaHit(
                area_id=area_id,
                priority=priority,
                hard=hard,
                score=score,
                matched=matched[:25],
                tags=list(tags)[:8],
            )
        )

    if not hits:
        return None, [], []

    # hard override: best (lowest priority) among hard hits
    hard_hits = [h for h in hits if h.hard]
    if hard_hits:
        hard_hits.sort(key=lambda h: (h.priority, -h.score, h.area_id))
        best = hard_hits[0]
        return best.area_id, best.tags[:3], hits

    # general best: priority first, then score
    hits.sort(key=lambda h: (h.priority, -h.score, h.area_id))

    # correspondence is last resort
    if hits[0].area_id == "08_KORRESPONDENZ" and any(h.area_id != "08_KORRESPONDENZ" for h in hits):
        best_non = next(h for h in hits if h.area_id != "08_KORRESPONDENZ")
        return best_non.area_id, best_non.tags[:3], hits

    best = hits[0]
    return best.area_id, best.tags[:3], hits


def frist_from_text(text: str, settings: Settings, *, base_date: Optional[str]) -> Optional[str]:
    if not base_date:
        return None
    t = _norm(text)
    triggers = settings.heuristics["frist"]["one_month_triggers"]
    for pat in triggers:
        try:
            if re.search(pat, t, flags=re.I):
                return add_one_month(base_date)
        except re.error:
            if _norm(pat) in t:
                return add_one_month(base_date)
    return None

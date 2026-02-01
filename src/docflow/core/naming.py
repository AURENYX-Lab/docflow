from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from typing import Optional

from src.docflow.settings import Settings


_UMLAUT = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"}
)


def ascii_slug(s: str, *, max_len: int) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.translate(_UMLAUT).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def coerce_iso_date(d: Optional[str]) -> Optional[str]:
    if not d:
        return None
    d = str(d).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return d
    return None


@dataclass(frozen=True)
class FilenamePolicy:
    schema: str
    max_total: int
    short_desc: int
    source: int
    status: int
    fallback_short: str
    fallback_source: str
    fallback_status: str

    @staticmethod
    def from_settings(settings: Settings) -> "FilenamePolicy":
        fn = settings.filenames
        limits = fn["limits"]
        fall = fn["fallbacks"]
        return FilenamePolicy(
            schema=str(fn["schema"]),
            max_total=int(limits["max_total"]),
            short_desc=int(limits["short_desc"]),
            source=int(limits["source"]),
            status=int(limits["status"]),
            fallback_short=str(fall["short"]),
            fallback_source=str(fall["source"]),
            fallback_status=str(fall["status"]),
        )


def build_suggested_filename(
    *,
    settings: Settings,
    iso_date: Optional[str],
    short_desc: Optional[str],
    source: Optional[str],
    status: Optional[str],
) -> str:
    pol = FilenamePolicy.from_settings(settings)

    d = coerce_iso_date(iso_date) or _date.today().isoformat()
    sd = ascii_slug(short_desc or pol.fallback_short, max_len=pol.short_desc) or pol.fallback_short
    src = ascii_slug(source or pol.fallback_source, max_len=pol.source) or pol.fallback_source
    st = ascii_slug(status or pol.fallback_status, max_len=pol.status) or pol.fallback_status

    out = pol.schema.format(date=d, short=sd, source=src, status=st)

    # final hardening
    out = re.sub(r"[^A-Za-z0-9_.\-]+", "_", out)
    out = re.sub(r"_+", "_", out).strip("_")
    if not out.lower().endswith(".pdf"):
        out += ".pdf"

    if len(out) > pol.max_total:
        base = out[:-4]
        base = base[: pol.max_total - 4].rstrip("_- .")
        out = base + ".pdf"

    return out

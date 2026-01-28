from __future__ import annotations
import re
from datetime import date


def slug(s: str, max_len: int = 40) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if s else ""


def make_suggested_filename(
    datum: str | None, kurz: str, quelle: str | None, status: str | None
) -> str:
    d = datum if datum and re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum) else "0000-00-00"
    k = slug(kurz, 40) or "dokument"
    q = slug(quelle or "quelle", 30) or "quelle"
    st = slug(status or "offen", 16) or "offen"
    return f"{d}_{k}_{q}_{st}.pdf"


def year_from_datum(datum: str | None) -> int:
    if datum and re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
        return int(datum[:4])
    return date.today().year

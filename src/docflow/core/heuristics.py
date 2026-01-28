from __future__ import annotations
import re
from datetime import date
import calendar

MONTHS = {
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


def extract_date(text: str) -> str | None:
    t = text.replace("\x00", " ").replace("\r", "\n")
    head = t[:8000]  # dates are almost always in header-ish parts

    # ISO
    m = re.search(r"\b((?:19|20)\d{2})-([01]\d)-([0-3]\d)\b", head)
    if m:
        return m.group(0)

    # Datum: dd.mm.yyyy
    m = re.search(
        r"\bDatum\s*:\s*([0-3]?\d)[.\-/ ]+([01]?\d)[.\-/ ]+((?:19|20)?\d{2})\b", head, re.I
    )
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), _norm_year(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except Exception:
            pass

    # vom/den dd.mm.yyyy
    m = re.search(
        r"\b(vom|den|ausgestellt\s+am)\s+([0-3]?\d)[.\-/ ]+([01]?\d)[.\-/ ]+((?:19|20)?\d{2})\b",
        head,
        re.I,
    )
    if m:
        d, mo, y = int(m.group(2)), int(m.group(3)), _norm_year(m.group(4))
        try:
            return date(y, mo, d).isoformat()
        except Exception:
            pass

    # month name
    m = re.search(
        r"\b([0-3]?\d)\.\s*(januar|februar|maerz|märz|april|mai|juni|juli|august|september|oktober|november|dezember)\s+((?:19|20)\d{2})\b",
        head,
        re.I,
    )
    if m:
        d = int(m.group(1))
        mo = MONTHS[m.group(2).lower()]
        y = int(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except Exception:
            pass

    # fallback: first plausible dd.mm.yyyy anywhere in head
    for m in re.finditer(r"\b([0-3]?\d)[.\-/ ]+([01]?\d)[.\-/ ]+((?:19|20)?\d{2})\b", head):
        d, mo, y = int(m.group(1)), int(m.group(2)), _norm_year(m.group(3))
        try:
            return date(y, mo, d).isoformat()
        except Exception:
            continue

    return None


def add_one_month_iso(d: str) -> str | None:
    try:
        y, m, day = map(int, d.split("-"))
    except Exception:
        return None
    nm = m + 1
    ny = y + (nm - 1) // 12
    nm = ((nm - 1) % 12) + 1
    last = calendar.monthrange(ny, nm)[1]
    nd = min(day, last)
    try:
        return date(ny, nm, nd).isoformat()
    except Exception:
        return None


def extract_aktenzeichen(text: str) -> list[str]:
    t = text.replace("\x00", " ").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)

    cands: list[str] = []

    # Labeled fields
    label_pat = re.compile(
        r"\b(?:Az\.?|Aktenzeichen|Gz\.?|Gesch\.?-?\s*Z(?:eichen)?|Geschäftszeichen|Mein\s+Zeichen|Zeichen|BG-?Nummer|Bedarfsgemeinschaft)\s*[:\-]?\s*"
        r"([A-Za-zÄÖÜäöüß0-9][A-Za-zÄÖÜäöüß0-9 .\-\/]{2,80})",
        re.I,
    )
    for m in label_pat.finditer(t):
        s = m.group(1).strip()
        # cut common trailing fields
        s = re.split(
            r"\s{2,}|\bDatum\b|\bSeite\b|\bTelefon\b|\bTelefax\b|\bE-?Mail\b", s, 1, flags=re.I
        )[0].strip()
        s = re.sub(r"\s+", " ", s)
        if len(s) >= 3 and re.search(r"\d", s):
            cands.append(s)

    # Court-style AZ patterns (rough but useful)
    court_pat = re.compile(
        r"\b(?:[A-Z]\s*)?\d{1,3}\s*[A-Z]{1,4}\s*\d{1,6}\/\d{2,4}(?:\s*[A-Z]{1,3})?(?:\s*[A-Z][a-z]{0,2})?\b"
    )
    for m in court_pat.finditer(t):
        cands.append(re.sub(r"\s+", " ", m.group(0)).strip())

    # BG-Nummer format like 66402//0031882
    for m in re.finditer(r"\b\d{3,8}\/\/\d{3,12}\b", t):
        cands.append(m.group(0))

    # Dedup & filter phone-like
    seen = set()
    out = []
    for s in cands:
        s = s.strip().strip(".,;")
        if not re.search(r"\d", s):
            continue
        if re.fullmatch(r"[0-9][0-9 \-()/]{6,}", s):
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[:12]


def guess_area(text: str) -> str:
    t = text.lower()

    def has(*w: str) -> bool:
        return any(x.lower() in t for x in w)

    # A) Recht/Behörden (strong)
    if has(
        "jobcenter",
        "bürgergeld",
        "sgb ii",
        "sgb2",
        "ablehnungsbescheid",
        "bescheid",
        "widerspruch",
        "klage",
        "sozialgericht",
        "verwaltungsgericht",
        "aktenzeichen",
        "rechtsbehelfsbelehr",
        "zustellung",
        "beA",
        "anwalt",
        "vollmacht",
        "kanzlei",
    ):
        return "05_RECHT_BEHOERDEN"

    # C) Versicherungen (before Gesundheit/Finanzen to avoid “Krankenkasse” misrouting)
    if has(
        "krankenkasse",
        "pflegeversicherung",
        "rentenversicherung",
        "berufsgenossenschaft",
        "versicherungsschein",
        "police",
        "leistungsbescheid",
    ):
        return "10_VERSICHERUNGEN"

    # B) Gesundheit
    if has(
        "klinik",
        "krankenhaus",
        "arzt",
        "therapie",
        "diagnose",
        "entlassungsbericht",
        "befund",
        "reha",
        "psychotherapie",
        "arbeitsunfähigkeit",
        "au",
    ):
        return "02_GESUNDHEIT"

    # D) Bildung/Beruf
    if has(
        "bafög",
        "bafoeg",
        "immatrikulation",
        "prüfungsamt",
        "prüfung",
        "leistungsnachweis",
        "praktikum",
        "arbeitsvertrag",
        "zeugnis",
        "hochschule",
        "iu",
    ):
        return "03_BILDUNG_BERUF"

    # E) Finanzen
    if has(
        "kontoauszug",
        "rechnung",
        "mahnung",
        "zahlung",
        "lastschrift",
        "finanzamt",
        "steuer",
        "kredit",
        "darlehen",
        "depot",
        "bank",
        "gebühren",
        "iban",
        "bic",
    ):
        return "04_FINANZEN"

    # F) Wohnen/Mobilität
    if has(
        "miete",
        "mietvertrag",
        "kaution",
        "nebskosten",
        "nebenkosten",
        "hausverwaltung",
        "wohnung",
        "öpnv",
        "bahn",
        "ticket",
        "kfz",
        "auto",
    ):
        return "06_WOHNEN_MOBILITAET"

    # K) System/Meta
    if has(
        "systemd",
        "journalctl",
        "stderr",
        "stacktrace",
        "traceback",
        "config",
        "yaml",
        "json",
        "logfile",
        "unit file",
        "bash",
        "python",
    ):
        return "98_SYSTEM_META"

    # J) Nachweise/Protokolle
    if has(
        "teilnahmebescheinigung",
        "bestätigung",
        "quittung",
        "einlieferungsbeleg",
        "protokoll",
        "nachweis",
    ):
        return "11_NACHWEISE_PROTOKOLLE"

    # I) Wissen/Referenzen
    if has(
        "doi",
        "abstract",
        "introduction",
        "literatur",
        "paper",
        "tutorial",
        "guide",
        "referenz",
        "notizen",
    ):
        return "09_WISSEN_REFERENZEN"

    # H) Projekte
    if has(
        "roadmap",
        "spec",
        "spezifikation",
        "todo",
        "aurenyx",
        "operator-system",
        "konzept",
        "projektplan",
    ):
        return "07_PROJEKTE"

    # L) Korrespondenz (nur wenn sonst nichts triggert)
    if has(
        "sehr geehrte", "mit freundlichen grüßen", "freundliche grüße", "email", "e-mail", "betreff"
    ):
        return "08_KORRESPONDENZ"

    # G) Persönlich fallback
    return "01_PERSOENLICH"


def guess_frist(text: str, area: str, datum: str | None) -> str | None:
    if area != "05_RECHT_BEHOERDEN" or not datum:
        return None
    t = text.lower()
    if (
        ("rechtsbehelfsbelehr" in t)
        or ("innerhalb eines monats" in t)
        or ("widerspruch" in t and "monat" in t)
        or ("klage" in t and "monat" in t)
    ):
        return add_one_month_iso(datum)
    return None

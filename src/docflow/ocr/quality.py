# docflow/src/docflow/ocr/quality.py
from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import pikepdf  # type: ignore

from docflow.settings import Settings


class OCRQualityError(RuntimeError):
    pass


# Heuristic: find text showing operators in content stream
_TEXT_OP = re.compile(rb"(?<![A-Za-z])(Tj|TJ|'|\")(?!(?:[A-Za-z]))")


@dataclass(frozen=True)
class QualityReport:
    skip_ocr: bool
    good_pages: int
    checked_pages: int
    coverage: float
    fonts: int
    total_pages: int
    avg_chars: int
    avg_words: int
    pdftotext_status: str  # "ok" | "partial" | "fail"


def _safe_pdffonts_count(pdf: Path) -> int:
    try:
        out = subprocess.check_output(
            ["pdffonts", str(pdf)], stderr=subprocess.DEVNULL
        ).decode("utf-8", errors="ignore")
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        # poppler prints 2 header lines typically
        return max(0, len(lines) - 2)
    except Exception:
        return -1


def _safe_pdftotext_page(pdf: Path, page_1based: int) -> Tuple[int, int, bool]:
    try:
        out = subprocess.check_output(
            [
                "pdftotext",
                "-f",
                str(page_1based),
                "-l",
                str(page_1based),
                str(pdf),
                "-",
            ],
            stderr=subprocess.DEVNULL,
        )
        txt = out.decode("utf-8", errors="ignore")
        txt = re.sub(r"\s+", " ", txt).strip()
        chars = len(txt)
        words = len(re.findall(r"\b\w+\b", txt))
        return chars, words, True
    except Exception:
        return 0, 0, False


def _evenly_spaced_indices(total_pages: int, n: int) -> List[int]:
    # 0-based indices, evenly spaced, deterministic
    if total_pages <= 0 or n <= 0:
        return []
    if total_pages == 1:
        return [0]
    if n == 1:
        return [0]
    idx = []
    for i in range(n):
        pos = round(i * (total_pages - 1) / (n - 1))
        idx.append(int(pos))
    return sorted(set(idx))


def _page_has_text_ops(page: pikepdf.Page) -> bool:
    contents = page.get("/Contents", None)
    if not contents:
        return False
    streams = contents if isinstance(contents, pikepdf.Array) else [contents]
    for s in streams:
        try:
            b = bytes(s.read_bytes())
            if _TEXT_OP.search(b):
                return True
        except Exception:
            continue
    return False


def assess_pdf_text_quality(
    pdf_path: Path,
    settings: Settings,
) -> QualityReport:
    q = settings.ocr.quality
    """
    Decide whether to skip OCR based on sampled pages.
    "Good page" = has text operators AND pdftotext chars/words above thresholds.
    """
    if not pdf_path.exists():
        raise OCRQualityError(f"PDF not found: {pdf_path}")

    fonts = _safe_pdffonts_count(pdf_path)

    try:
        with pikepdf.open(str(pdf_path)) as pdf:
            total_pages = len(pdf.pages)
    except Exception as e:
        raise OCRQualityError(f"Failed to open PDF (pikepdf): {pdf_path} ({e})") from e

    if total_pages <= 0:
        return QualityReport(
            skip_ocr=False,
            good_pages=0,
            checked_pages=0,
            coverage=0.0,
            fonts=fonts,
            total_pages=0,
            avg_chars=0,
            avg_words=0,
            pdftotext_status="fail",
        )

    needed = int(math.ceil(total_pages * q.sample_pct))
    checked = max(q.sample_min_pages, needed)
    checked = min(checked, q.pages_cap, total_pages)

    indices = _evenly_spaced_indices(total_pages, checked)

    good = 0
    chars_sum = 0
    words_sum = 0
    pt_ok_all = True

    # Re-open once to access pages (avoid holding streams too long)
    with pikepdf.open(str(pdf_path)) as pdf:
        for idx in indices:
            page = pdf.pages[idx]
            has_ops = _page_has_text_ops(page)
            chars, words, pt_ok = _safe_pdftotext_page(pdf_path, idx + 1)
            pt_ok_all = pt_ok_all and pt_ok
            chars_sum += chars
            words_sum += words
            if (
                has_ops
                and chars >= q.min_chars_per_page
                and words >= q.min_words_per_page
            ):
                good += 1

    coverage = (good / checked) if checked else 0.0
    skip = coverage >= q.min_text_pages

    avg_chars = int(round(chars_sum / checked)) if checked else 0
    avg_words = int(round(words_sum / checked)) if checked else 0

    pt_status = "ok" if pt_ok_all else "partial"
    return QualityReport(
        skip_ocr=skip,
        good_pages=good,
        checked_pages=checked,
        coverage=coverage,
        fonts=fonts,
        total_pages=total_pages,
        avg_chars=avg_chars,
        avg_words=avg_words,
        pdftotext_status=pt_status,
    )

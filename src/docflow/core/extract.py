from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import pikepdf  # type: ignore


class ExtractError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractPlan:
    max_chars: int
    front_pages: int
    dist_pages: int


def num_pages(pdf_path: Path) -> int:
    with pikepdf.open(str(pdf_path)) as pdf:
        return len(pdf.pages)


def _evenly_spaced_indices(total: int, n: int) -> List[int]:
    if total <= 0:
        return []
    if n <= 1:
        return [0]
    if total == 1:
        return [0]
    idx = []
    for i in range(n):
        pos = round(i * (total - 1) / (n - 1))
        idx.append(int(pos))
    return sorted(set(idx))


def _pdftotext_one_page(pdf_path: Path, page_1based: int, *, timeout_s: int = 30) -> str:
    try:
        out = subprocess.check_output(
            ["pdftotext", "-f", str(page_1based), "-l", str(page_1based), str(pdf_path), "-"],
            stderr=subprocess.DEVNULL,
            timeout=timeout_s,
        )
        return out.decode("utf-8", errors="ignore").replace("\x00", "")
    except Exception:
        return ""


def sample_text(pdf_path: Path, plan: ExtractPlan) -> str:
    """
    Deterministic sampling across PDF:
    - always take first N front pages
    - take evenly spaced dist pages across whole doc
    - budget is in characters (roughly), but we enforce by UTF-8 byte truncation to be safe.
    """
    total = num_pages(pdf_path)
    if total <= 0:
        return ""

    front = list(range(1, min(plan.front_pages, total) + 1))
    dist_idx = _evenly_spaced_indices(total, min(plan.dist_pages, total))
    dist = [i + 1 for i in dist_idx]

    # ordered unique
    pages: List[int] = []
    seen = set()
    for p in front + dist:
        if p not in seen:
            pages.append(p)
            seen.add(p)

    chunks: List[str] = []
    for p in pages:
        chunks.append(_pdftotext_one_page(pdf_path, p))
        chunks.append("\n")

    raw = "".join(chunks).strip()

    # enforce max_chars using UTF-8 bytes to avoid breaking multi-byte sequences
    b = raw.encode("utf-8", errors="ignore")
    # rough char->byte guard: allow ~4 bytes per char worst-case
    max_bytes = max(1024, min(len(b), plan.max_chars * 4))
    b2 = b[:max_bytes]
    txt = b2.decode("utf-8", errors="ignore")

    # final trim to max_chars
    if len(txt) > plan.max_chars:
        txt = txt[: plan.max_chars]
    return txt.strip()

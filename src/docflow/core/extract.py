from __future__ import annotations
from pathlib import Path
import math
import subprocess
import pikepdf


def pdf_page_count(pdf: Path) -> int:
    with pikepdf.open(str(pdf)) as f:
        return len(f.pages)


def sample_pages(total: int, front: int, dist: int, start_pct: int, end_pct: int) -> list[int]:
    if total <= 0:
        return []
    pages = []

    # front pages
    for i in range(1, min(front, total) + 1):
        pages.append(i)

    # distributed range
    if dist > 0 and total > 1:
        a = max(0, min(100, start_pct)) / 100.0
        b = max(0, min(100, end_pct)) / 100.0
        if b < a:
            a, b = b, a

        start = max(0, int(math.floor((total - 1) * a)))
        end = min(total - 1, int(math.floor((total - 1) * b)))
        if end < start:
            start, end = 0, total - 1

        span = end - start
        if span == 0:
            idxs = [start]
        else:
            if dist == 1:
                idxs = [start + span // 2]
            else:
                idxs = [round(start + i * span / (dist - 1)) for i in range(dist)]

        for ix in sorted(set(int(x) for x in idxs)):
            p = ix + 1
            if 1 <= p <= total:
                pages.append(p)

    # last page
    pages.append(total)

    # unique in order
    seen = set()
    out = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def pdftotext_pages(pdf: Path, pages: list[int]) -> bytes:
    out = bytearray()
    for p in pages:
        cp = subprocess.run(
            ["pdftotext", "-f", str(p), "-l", str(p), "-layout", str(pdf), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        chunk = cp.stdout.replace(b"\x00", b"")
        out.extend(chunk)
        out.extend(b"\n")
    return bytes(out)


def extract_text_budget(
    pdf: Path, max_bytes: int, front_pages: int, dist_pages: int, start_pct: int, end_pct: int
) -> str:
    total = pdf_page_count(pdf)
    pages = sample_pages(total, front_pages, dist_pages, start_pct, end_pct)
    raw = pdftotext_pages(pdf, pages)
    raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="ignore")

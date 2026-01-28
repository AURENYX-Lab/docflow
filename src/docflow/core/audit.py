from __future__ import annotations
from pathlib import Path
import csv
import hashlib
from datetime import datetime


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def utc_ts() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def manifest_path(logs_dir: Path) -> Path:
    return logs_dir / "manifest.csv"


def append_manifest(logs_dir: Path, row: dict[str, str]) -> None:
    mp = manifest_path(logs_dir)
    new = not mp.exists()
    with mp.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sorted(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)

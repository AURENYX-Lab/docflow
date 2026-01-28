from __future__ import annotations
from pathlib import Path
from datetime import datetime
import re


def safe_note_name(name: str) -> str:
    # avoid characters obsidian/fs hates
    name = re.sub(r"[\/\\\:\*\?\"<>\|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] if name else "Dokument"


def write_note(
    vault: Path, notes_root: str, area: str, year: int, title: str, body_md: str
) -> Path:
    root = vault / notes_root / area / str(year)
    root.mkdir(parents=True, exist_ok=True)
    fn = safe_note_name(title) + ".md"
    path = root / fn
    path.write_text(body_md, encoding="utf-8")
    return path


def make_note_markdown(
    meta: dict, pdf_path: Path, pdf_sha: str, text_sha: str, applied_at: str
) -> str:
    y = meta["yaml"]
    frontmatter = {
        "typ": y.get("typ"),
        "bereich": y.get("bereich"),
        "datum": y.get("datum"),
        "quelle": y.get("quelle"),
        "aktenzeichen": y.get("aktenzeichen", []),
        "frist": y.get("frist"),
        "status": y.get("status"),
        "tags": y.get("tags", []),
        "input_pdf": meta.get("input_pdf"),
        "archiv_pdf": str(pdf_path),
        "sha256_pdf": pdf_sha,
        "sha256_text": text_sha,
        "applied_at_utc": applied_at,
    }

    fm_lines = ["---"]
    for k, v in frontmatter.items():
        fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")

    kp = meta.get("key_points", [])
    kp_md = "\n".join([f"- {x}" for x in kp]) if kp else "- (keine)"

    md = "\n".join(fm_lines) + "\n\n"
    md += f"# {meta.get('doc_title','Dokument')}\n\n"
    md += f"**PDF:** `{pdf_path}`\n\n"
    md += f"## Summary\n{meta.get('summary','')}\n\n"
    md += f"## Key Points\n{kp_md}\n"
    return md

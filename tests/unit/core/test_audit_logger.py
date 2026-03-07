from __future__ import annotations

import json
from pathlib import Path
import pytest

from docflow.core.audit import AuditLogger, sha256_file


PDF_A = b"%PDF-1.4\nA\n%%EOF\n"
PDF_B = b"%PDF-1.4\nB\n%%EOF\n"


def test_sha256_file_changes_on_content_change(tmp_path: Path) -> None:
    p = tmp_path / "x.pdf"
    p.write_bytes(PDF_A)
    h1 = sha256_file(p)

    p.write_bytes(PDF_B)
    h2 = sha256_file(p)

    assert h1 != h2


def test_audit_logger_writes_jsonl_events(tmp_path: Path) -> None:
    manifest = tmp_path / "audit.jsonl"
    a = AuditLogger(manifest_path=manifest, settings_sha256="testsha256")

    in_pdf = tmp_path / "in.pdf"
    out_pdf = tmp_path / "out.pdf"
    in_pdf.write_bytes(PDF_A)
    out_pdf.write_bytes(PDF_A)

    a.event(kind="apply.start", input_path=in_pdf, meta={"x": 1})
    a.event(kind="apply.done", input_path=in_pdf, output_path=out_pdf, meta={"ok": True})

    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, f"expected 2 jsonl lines, got {len(lines)}"

    e1 = json.loads(lines[0])
    e2 = json.loads(lines[1])

    assert e1["kind"] == "apply.start"
    assert e2["kind"] == "apply.done"

    # Hashes should be present when paths are present
    assert "input_sha256" in e1
    assert e2.get("output_sha256") is not None

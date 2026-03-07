from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.integration
def test_apply_dry_run_does_not_write_to_archiv(
    run_integration: bool, tmp_path: Path, tmp_settings_dir: Path
) -> None:
    if not run_integration:
        pytest.skip("set RUN_INTEGRATION=1 to run integration tests")

    # layout
    archiv = tmp_path / "ARCHIV"
    inbox = tmp_path / "INBOX"
    out = tmp_path / "OUT"
    logs = tmp_path / "LOGS"
    inbox.mkdir()
    out.mkdir()
    logs.mkdir()

    # create input pdf
    pdf = inbox / "in.pdf"
    pdf.write_bytes(b"%PDF-1.4\nX\n%%EOF\n")

    # create a minimal suggestion JSON in OUT (same naming as suggest pipeline)
    sj = out / f"{pdf.name}.suggest.json"
    sug = {
        "input_pdf": str(pdf),
        "suggested_area": "A",
        "suggested_year": 2024,
        "suggested_filename": "in.pdf",
        "doc_type": "DT",
        "doc_title": "t",
        "summary": "s",
        "key_points": ["k"],
        "yaml": {
            "typ": "DT",
            "bereich": "A",
            "datum": None,
            "quelle": None,
            "aktenzeichen": [],
            "frist": None,
            "status": None,
            "tags": [],
        },
        "approved": True,
    }
    sj.write_text(json.dumps(sug, ensure_ascii=False, indent=2), encoding="utf-8")

    # run CLI apply dry-run with overrides
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    cp = subprocess.run(
        [
            sys.executable,
            "-m",
            "docflow",
            "--settings-dir",
            str(tmp_settings_dir),
            "--archiv-root",
            str(archiv),
            "--inbox-dir",
            str(inbox),
            "apply",
            "--dry-run",
            "--suggestions-dir",
            str(out),
            "--log-dir",
            str(logs),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert cp.returncode == 0, cp.stderr
    assert not archiv.exists() or not any(
        archiv.rglob("*.pdf")
    ), "dry-run must not create archived PDFs"

# docflow/src/docflow/ocr/preflight.py
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional


class PreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreflightReport:
    ok: bool
    missing_tools: List[str]
    python_deps_ok: bool
    notes: List[str]


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _check_cmd_version(cmd: List[str]) -> bool:
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except Exception:
        return False


def run_preflight(*, strict: bool = True) -> PreflightReport:
    """
    Verifies external tools + python deps exist.
    strict=True => raise PreflightError on failure.
    """
    missing: List[str] = []
    notes: List[str] = []

    required_tools = ["ocrmypdf", "pdftotext", "pdffonts"]
    for t in required_tools:
        if _which(t) is None:
            missing.append(t)

    # quick sanity call (avoid false positives where binary exists but fails hard)
    if "ocrmypdf" not in missing and not _check_cmd_version(["ocrmypdf", "--version"]):
        notes.append("ocrmypdf exists but '--version' call failed (check installation)")
    if "pdftotext" not in missing and not _check_cmd_version(["pdftotext", "-v"]):
        notes.append("pdftotext exists but '-v' call failed (check poppler-utils)")
    if "pdffonts" not in missing and not _check_cmd_version(["pdffonts", "-v"]):
        notes.append("pdffonts exists but '-v' call failed (check poppler-utils)")

    # python deps
    python_ok = True
    try:
        import pikepdf  # noqa: F401
    except Exception:
        python_ok = False
        notes.append("Missing python dependency: pikepdf")

    ok = (len(missing) == 0) and python_ok

    if strict and not ok:
        msg = "OCR preflight failed:\n"
        if missing:
            msg += f"- missing tools: {', '.join(missing)}\n"
        if not python_ok:
            msg += "- missing python deps: pikepdf\n"
        if notes:
            msg += "- notes:\n  " + "\n  ".join(notes) + "\n"
        raise PreflightError(msg.rstrip())

    return PreflightReport(ok=ok, missing_tools=missing, python_deps_ok=python_ok, notes=notes)

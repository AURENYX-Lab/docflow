# docflow/src/docflow/ocr/pipeline.py
from __future__ import annotations

import os
import time
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from docflow.core.config import AppConfig
from docflow.ocr.preflight import run_preflight
from docflow.ocr.quality import (
    QualityReport,
    OCRQualityError,
    assess_pdf_text_quality,
)


class OCRPipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCRPaths:
    inbox_dir: Path
    log_dir: Path
    quarantine_dir: Path


@dataclass(frozen=True)
class OCRRunOptions:
    dry_run: bool = False
    limit: int = 0
    force: bool = False  # if True: run OCR even if quality says "skip"
    copy_instead_of_replace: bool = False  # usually False: replace original


@dataclass(frozen=True)
class OCRStats:
    total_seen: int
    would_ocr: int
    ocred: int
    skipped: int
    errors: int
    quarantined: int


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _log(log_file: Path, msg: str) -> None:
    _append_line(log_file, f"[{_ts()}] {msg}")


def _err(err_file: Path, msg: str) -> None:
    _append_line(err_file, f"[{_ts()}] [OCR] {msg}")


def _is_artifact(filename: str) -> bool:
    base = filename.lower()
    if base.endswith(".ocr.pdf"):
        return True
    if ".ocr_tmp." in base:
        return True
    if base.endswith(".ocr_tmp.pdf"):
        return True
    return False


def _fail_marker_for(log_dir: Path, pdf: Path) -> Path:
    # stable per file path marker (not content hash)
    h = hashlib.sha1(str(pdf).encode("utf-8", errors="ignore")).hexdigest()
    return log_dir / f"{h}.ocr_failed"


def _format_quality(q: QualityReport) -> str:
    return (
        f"fonts={q.fonts} checked_pages={q.checked_pages} total_pages={q.total_pages} "
        f"avg_chars={q.avg_chars} avg_words={q.avg_words} pdftotext={q.pdftotext_status} "
        f"coverage {q.good_pages}/{q.checked_pages}={q.coverage:.6f}"
    )


def _mktemp_out(pdf: Path) -> Path:
    # create tmp next to pdf for atomic replace
    rnd = os.urandom(6).hex()
    return pdf.with_name(f".{pdf.name}.ocr_tmp.{rnd}.pdf")


def _build_ocrmypdf_args(cfg: AppConfig) -> List[str]:
    """
    Build deterministic ocrmypdf CLI args from Pydantic runtime settings:
      cfg.settings.ocr.ocrmypdf
    """
    settings = cfg.settings
    o = cfg.settings.ocr.ocrmypdf

    args: List[str] = []

    # languages + parallelism
    args += ["-l", str(o.langs)]
    args += ["-j", str(int(o.jobs))]

    # output format
    # (ocrmypdf uses: --output-type pdfa/pdf/none)
    args += ["--output-type", str(o.output_type)]

    # optimization level
    args += ["--optimize", str(int(o.optimize))]

    # boolean flags
    if bool(o.clean):
        args.append("--clean")
    if bool(o.deskew):
        args.append("--deskew")
    if bool(o.rotate_pages):
        args.append("--rotate-pages")

    # pass-through extra args (must be stable, no defaults hidden)
    extra = list(getattr(o, "extra_args", []) or [])
    args += [str(x) for x in extra]

    return args


def run_ocr_inbox(
    *,
    cfg: AppConfig,
    paths: OCRPaths,
    options: OCRRunOptions,
) -> OCRStats:
    """
    Scans inbox_dir (maxdepth=1) for PDFs and OCRs them if quality gate says needed.
    Replaces originals atomically unless copy_instead_of_replace=True.
    Quarantines repeated failures.

    Pydantic runtime truth:
      - Quality gate config: cfg.settings.ocr.quality
      - OCR args config:     cfg.settings.ocr.ocrmypdf
    """
    run_preflight(strict=True)

    paths.log_dir.mkdir(parents=True, exist_ok=True)
    paths.quarantine_dir.mkdir(parents=True, exist_ok=True)
    paths.inbox_dir.mkdir(parents=True, exist_ok=True)

    log_file = paths.log_dir / "ocrmypdf.log"
    err_file = paths.log_dir / "docflow_error.log"

    qset = cfg.settings.ocr.quality
    ocrmypdf_args = _build_ocrmypdf_args(cfg)

    _log(log_file, "==== OCR run started ====")
    _log(
        log_file,
        "Settings: "
        f"LANGS={cfg.settings.ocr.ocrmypdf.langs} JOBS={cfg.settings.ocr.ocrmypdf.jobs} "
        f"PAGES_CAP={qset.pages_cap} SAMPLE_PCT={qset.sample_pct} SAMPLE_MIN_PAGES={qset.sample_min_pages} "
        f"MIN_TEXT_PAGES={qset.min_text_pages} MIN_CHARS_PER_PAGE={qset.min_chars_per_page} "
        f"MIN_WORDS_PER_PAGE={qset.min_words_per_page} OUTPUT_TYPE={cfg.settings.ocr.ocrmypdf.output_type} "
        f"OPTIMIZE={cfg.settings.ocr.ocrmypdf.optimize}",
    )

    total_seen = would_ocr = ocred = skipped = errors = quarantined = 0

    pdfs = sorted(
        [p for p in paths.inbox_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"]
    )

    processed = 0
    for pdf in pdfs:
        if options.limit > 0 and processed >= options.limit:
            break
        processed += 1

        base = pdf.name
        if _is_artifact(base):
            _log(log_file, f"SKIP (artifact): {base}")
            skipped += 1
            continue

        total_seen += 1

        # Quality gate
        qrep: Optional[QualityReport] = None
        try:
            qrep = assess_pdf_text_quality(pdf, qset)
        except OCRQualityError as e:
            # fallback: OCR (warn)
            _log(log_file, f"Quality check failed (fallback to OCR): {base} ({e})")
            _err(err_file, f"Quality check failed (fallback to OCR): {base} ({e})")

        if qrep is not None and qrep.skip_ocr and not options.force:
            _log(log_file, f"SKIP ({_format_quality(qrep)}): {base}")
            skipped += 1
            continue

        # OCR run
        tmp_out = _mktemp_out(pdf)
        if qrep is not None:
            _log(log_file, f"OCR start ({_format_quality(qrep)}): {base}")
        else:
            _log(log_file, f"OCR start (quality=?): {base}")

        if options.dry_run:
            _log(log_file, f"DRY-RUN: would run ocrmypdf on {base}")
            would_ocr += 1
            try:
                if tmp_out.exists():
                    tmp_out.unlink()
            except Exception:
                pass
            continue

        cmd = ["ocrmypdf", *ocrmypdf_args, str(pdf), str(tmp_out)]

        try:
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
            )
            out = proc.stdout.decode("utf-8", errors="ignore")
            if out.strip():
                _append_line(log_file, out.rstrip("\n"))

            if proc.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 0:
                if options.copy_instead_of_replace:
                    out_pdf = pdf.with_name(pdf.stem + ".ocr.pdf")
                    os.replace(tmp_out, out_pdf)
                    _log(log_file, f"OCR done (wrote output): {out_pdf.name}")
                else:
                    os.replace(tmp_out, pdf)
                    _log(log_file, f"OCR done (replaced original): {base}")

                ocred += 1

                # clear fail marker if present
                try:
                    _fail_marker_for(paths.log_dir, pdf).unlink(missing_ok=True)
                except Exception:
                    try:
                        fm = _fail_marker_for(paths.log_dir, pdf)
                        if fm.exists():
                            fm.unlink()
                    except Exception:
                        pass
            else:
                raise OCRPipelineError(f"ocrmypdf failed rc={proc.returncode}")

        except Exception as e:
            errors += 1
            _err(err_file, f"OCR failed: {base} ({e})")
            _log(log_file, f"ERROR: OCR failed: {base} ({e})")

            # cleanup tmp
            try:
                if tmp_out.exists():
                    tmp_out.unlink()
            except Exception:
                pass

            # quarantine after repeated failures
            fm = _fail_marker_for(paths.log_dir, pdf)
            if fm.exists():
                _err(err_file, f"Quarantine: {base} (repeated OCR failure)")
                _log(log_file, f"ERROR: Quarantine: {base} (repeated OCR failure)")
                try:
                    target = paths.quarantine_dir / base
                    if not target.exists():
                        os.replace(pdf, target)
                    else:
                        stamped = paths.quarantine_dir / f"{pdf.stem}__{int(time.time())}.pdf"
                        os.replace(pdf, stamped)
                    quarantined += 1
                    try:
                        fm.unlink()
                    except Exception:
                        pass
                except Exception as qe:
                    _err(err_file, f"Failed to move to quarantine: {base} ({qe})")
                    _log(log_file, f"ERROR: Failed to move to quarantine: {base} ({qe})")
            else:
                try:
                    fm.write_text("1", encoding="utf-8")
                except Exception:
                    pass

    _log(log_file, "==== OCR run finished ====")
    if options.dry_run:
        _log(
            log_file,
            f"Total: {total_seen} | Would-OCR: {would_ocr} | Skipped: {skipped} | Errors: {errors} | Quarantine: {quarantined}",
        )
    else:
        _log(
            log_file,
            f"Total: {total_seen} | OCRed: {ocred} | Skipped: {skipped} | Errors: {errors} | Quarantine: {quarantined}",
        )

    return OCRStats(
        total_seen=total_seen,
        would_ocr=would_ocr,
        ocred=ocred,
        skipped=skipped,
        errors=errors,
        quarantined=quarantined,
    )

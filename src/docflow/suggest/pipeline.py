# docflow/src/docflow/suggest/pipeline.py
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from docflow.core.extract import build_text_budgeted_sample
from docflow.core.schema import DOCFLOW_JSON_SCHEMA

from .jsonfix import extract_and_parse_json
from .ollama_client import OllamaClient
from .postprocess import _heuristic_base_from_extraction, postprocess_suggestion
from .prompt import SuggestPrompt
from .verify import verify_suggestion


@dataclass(frozen=True)
class SuggestPaths:
    inbox_dir: Path
    out_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class SuggestOptions:
    dry_run: bool = False
    limit: int = 0
    force: bool = False
    use_llm: bool = True


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _log(paths: SuggestPaths, msg: str) -> None:
    _append_line(paths.log_dir / "docflow_suggest.log", f"[{_ts()}] {msg}")


def _err(paths: SuggestPaths, msg: str) -> None:
    _append_line(paths.log_dir / "docflow_error.log", f"[{_ts()}] [SUGGEST] {msg}")


def _suggestion_path(out_dir: Path, pdf: Path) -> Path:
    return out_dir / f"{pdf.name}.suggest.json"


def _raw_path(out_dir: Path, pdf: Path) -> Path:
    return out_dir / f"{pdf.name}.llm_raw.txt"


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run_suggest_batch(
    *,
    cfg,  # AppConfig
    paths: SuggestPaths,
    options: SuggestOptions,
) -> None:
    paths.out_dir.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)

    settings = cfg.settings

    allowed_areas = cfg.allowed_area_ids()
    allowed_doc_types = cfg.allowed_doc_type_ids()
    if not allowed_areas:
        raise SystemExit("Keine Areas in settings/categories.yaml definiert.")

    prompt = SuggestPrompt.from_settings(settings)
    timeout_s = int(settings.pipeline.suggest.ollama_timeout_s)
    client = OllamaClient(model=cfg.llm.ollama_model, timeout_s=timeout_s)

    pdfs = sorted(
        [
            p
            for p in paths.inbox_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf"
        ]
    )

    processed = 0
    for pdf in pdfs:
        if options.limit > 0 and processed >= options.limit:
            break
        processed += 1

        out_json = _suggestion_path(paths.out_dir, pdf)
        out_raw = _raw_path(paths.out_dir, pdf)

        if out_json.exists() and not options.force:
            _log(paths, f"SKIP (exists): {pdf.name}")
            continue

        try:
            extracted = build_text_budgeted_sample(cfg, pdf)
        except Exception as e:
            _err(paths, f"{pdf.name} extract failed: {type(e).__name__}: {e}")
            continue

        # deterministic heuristic base for human-readable, no-llm suggestions
        heuristic_base = _heuristic_base_from_extraction(
            settings=settings,
            extracted_text=extracted,
            allowed_areas=allowed_areas,
            allowed_doc_types=allowed_doc_types,
        )

        heuristic_hint = {
            "note": "Heuristics are a hint; output must match schema and allowed areas.",
            "allowed_areas": list(allowed_areas),
        }

        user_prompt = prompt.render(
            input_pdf=str(pdf),
            extracted_text=extracted,
            allowed_areas=allowed_areas,
            allowed_doc_types=allowed_doc_types,
            schema=DOCFLOW_JSON_SCHEMA,
            heuristics_hint=heuristic_hint,
        )

        llm_obj: Optional[Dict[str, Any]] = None

        use_llm_effective = bool(options.use_llm and settings.pipeline.suggest.use_llm)

        # llm_fallback_only: only call LLM if heuristics did not yield something meaningful.
        if use_llm_effective and bool(
            getattr(settings.pipeline.suggest, "llm_fallback_only", False)
        ):
            area_guess = str(heuristic_base.get("area") or "").strip() or None
            # simplest rule: only call LLM if area is missing/unsorted
            if not area_guess or area_guess == "UNSORTIERT":
                pass
            else:
                use_llm_effective = False

        if use_llm_effective:
            if options.dry_run:
                _log(paths, f"DRY-RUN: would call LLM for {pdf.name}")
            else:
                res = client.run(prompt.system + "\n\n" + user_prompt)
                if res.stderr.strip():
                    _err(paths, f"{pdf.name} ollama stderr: {res.stderr[:5000]}")
                if not res.ok:
                    _err(
                        paths,
                        f"{pdf.name} ollama failed rc={res.returncode} timed_out={res.timed_out}",
                    )
                else:
                    out_raw.write_text(res.stdout, encoding="utf-8", errors="ignore")

                    parsed = extract_and_parse_json(res.stdout)
                    if not parsed.ok or not isinstance(parsed.obj, dict):
                        _err(paths, f"{pdf.name} JSON parse failed: {parsed.error}")
                    else:
                        llm_obj = parsed.obj

        pp = postprocess_suggestion(
            settings=settings,
            input_pdf=str(pdf),
            extracted_text=extracted,
            allowed_areas=allowed_areas,
            allowed_doc_types=allowed_doc_types,
            llm_obj=llm_obj,
            heuristic_base=heuristic_base,
        )

        vr = verify_suggestion(
            pp.suggestion,
            settings=settings,
            allowed_areas=allowed_areas,
            allowed_doc_types=allowed_doc_types,
            min_year=int(settings.heuristics.date_detection.min_year),
            max_year=int(settings.heuristics.date_detection.max_year),
        )
        if not vr.ok:
            _err(paths, f"{pdf.name} suggestion invalid: {' | '.join(vr.errors)}")
            pp.suggestion["_invalid"] = True
            pp.suggestion["_errors"] = vr.errors

        if options.dry_run:
            _log(paths, f"DRY-RUN: would write {out_json.name}")
            continue

        _write_json(out_json, pp.suggestion)

        if pp.warnings:
            _log(paths, f"{pdf.name} warnings: {' | '.join(pp.warnings)}")

        _log(paths, f"OK: {pdf.name} -> {out_json.name}")

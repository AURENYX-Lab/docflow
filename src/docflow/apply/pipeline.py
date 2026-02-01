# docflow/src/docflow/apply/pipeline.py
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from docflow.apply.filesystem import copy_or_move_pdf
from docflow.apply.obsidian import NotePolicy, write_note
from docflow.apply.verify import (
    ApprovalPolicy,
    get_input_pdf_path,
    is_approved,
    load_suggestion_json,
)
from docflow.core.audit import AuditLogger


class ApplyPipelineError(RuntimeError):
    pass


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append_line(p: Path, line: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


@dataclass(frozen=True)
class ApplyPaths:
    suggestions_dir: Path
    log_dir: Path


@dataclass(frozen=True)
class ApplyOptions:
    dry_run: bool = False
    limit: int = 0
    force: bool = False  # apply even if not approved (danger)
    mode: str = "copy"  # "copy" | "move"


def _require(d: Dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise ApplyPipelineError(f"Missing required setting: {path}")
        cur = cur[part]
    return cur


def _log(paths: ApplyPaths, msg: str) -> None:
    _append_line(paths.log_dir / "docflow_apply.log", f"[{_ts()}] {msg}")


def _err(paths: ApplyPaths, msg: str) -> None:
    _append_line(paths.log_dir / "docflow_error.log", f"[{_ts()}] [APPLY] {msg}")


def _dest_pdf_path(cfg, suggestion: Dict[str, Any]) -> Path:
    area = suggestion["suggested_area"]
    year = int(suggestion["suggested_year"])
    fname = suggestion["suggested_filename"]
    return (cfg.paths.archiv_root / area / str(year) / fname).resolve()


def run_apply_batch(
    *,
    cfg,
    paths: ApplyPaths,
    options: ApplyOptions,
) -> None:
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    settings = cfg.settings

    allowed = cfg.allowed_area_ids()

    ap = settings.pipeline.apply
    collision = ap.collision_policy
    audit_manifest = Path(ap.audit_manifest).expanduser().resolve()

    approval_policy = ApprovalPolicy.from_settings(settings)
    write_obsidian = bool(ap.write_obsidian_note)
    note_policy = NotePolicy.from_settings(settings) if write_obsidian else None

    auditor = AuditLogger(
        manifest_path=audit_manifest,
        settings_sha256=settings.settings_sha256,
    )

    # collect suggestions
    sug_files = sorted(
        [p for p in paths.suggestions_dir.iterdir() if p.is_file() and p.name.endswith(".json")]
    )

    approval_mode = approval_policy.mode  # "json_flag" | "sidecar_file"
    approval_meta = {
        "mode": approval_mode,
        "json_flag_field": getattr(approval_policy, "json_flag_field", None),
        "json_flag_value": getattr(approval_policy, "json_flag_value", None),
        "sidecar_suffix": getattr(approval_policy, "sidecar_suffix", None),
    }

    processed = 0
    for sj in sug_files:
        if options.limit > 0 and processed >= options.limit:
            break
        processed += 1

        try:
            rec = load_suggestion_json(sj)
        except Exception as e:
            _err(paths, f"{sj.name}: load/validate failed: {type(e).__name__}: {e}")
            continue

        # approval gate
        approved = bool(options.force or is_approved(rec, approval_policy))
        if not approved:
            _log(paths, f"SKIP (not approved): {sj.name}")
            continue

        sug = rec.data

        # sanity: allowed areas
        if sug.get("suggested_area") not in allowed:
            _err(paths, f"{sj.name}: suggested_area not allowed: {sug.get('suggested_area')}")
            continue

        src_pdf = None
        try:
            src_pdf = get_input_pdf_path(rec)
        except Exception as e:
            _err(paths, f"{sj.name}: missing/invalid input_pdf: {e}")
            continue

        if not src_pdf.exists():
            _err(paths, f"{sj.name}: input_pdf missing on disk: {src_pdf}")
            continue

        dst_pdf = _dest_pdf_path(cfg, sug)
        if options.dry_run:
            auditor.event(
                kind="apply.dry_run",
                input_path=src_pdf,
                output_path=dst_pdf,
                meta={
                    "suggestion_json": str(sj),
                    "approval": approval_meta,
                    "approved": approved,
                    "forced": bool(options.force),
                    "mode": options.mode,
                    "collision_policy": collision,
                    "dest_pdf": str(dst_pdf),
                },
            )
            _log(paths, f"DRY-RUN: would {options.mode} {src_pdf.name} -> {dst_pdf}")
            continue

        # ab hier: echter Apply Run
        auditor.event(
            kind="apply.start",
            input_path=src_pdf,
            output_path=dst_pdf,
            meta={
                "suggestion_json": str(sj),
                "approval": approval_meta,
                "approved": approved,
                "forced": bool(options.force),
                "mode": options.mode,
                "collision_policy": collision,
                "dest_pdf": str(dst_pdf),
            },
        )

        try:
            res = copy_or_move_pdf(
                src=src_pdf,
                dst=dst_pdf,
                mode=options.mode,
                collision=collision,
            )
        except Exception as e:
            _err(paths, f"{sj.name}: file op failed: {type(e).__name__}: {e}")
            auditor.event(
                kind="apply.error",
                input_path=src_pdf,
                output_path=dst_pdf,
                meta={
                    "suggestion_json": str(sj),
                    "approval": approval_meta,
                    "approved": approved,
                    "forced": bool(options.force),
                    "mode": options.mode,
                    "collision_policy": collision,
                    "dest_pdf": str(dst_pdf),
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
            )
            continue

        # write obsidian note
        note_path: Optional[Path] = None
        if write_obsidian and note_policy is not None:
            try:
                note_path = write_note(
                    policy=note_policy,
                    suggestion=sug,
                    archived_pdf_path=res.dst,
                    archived_pdf_sha256=res.dst_sha256,
                    suggestion_json_path=sj,
                    settings_sha256=settings.settings_sha256,
                )
            except Exception as e:
                _err(paths, f"{sj.name}: obsidian note failed: {type(e).__name__}: {e}")
                auditor.event(
                    kind="apply.note_error",
                    input_path=res.src,
                    output_path=res.dst,
                    meta={
                        "suggestion_json": str(sj),
                        "forced": bool(options.force),
                        "mode": options.mode,
                        "collision_policy": collision,
                        "error_type": type(e).__name__,
                        "error": str(e),
                    },
                )

        auditor.event(
            kind="apply.done",
            input_path=res.src,
            output_path=res.dst,
            meta={
                "suggestion_json": str(sj),
                "approval": approval_meta,
                "forced": bool(options.force),
                "mode": options.mode,
                "collision_policy": collision,
                "src_sha256": res.src_sha256,
                "dst_sha256": res.dst_sha256,
                "changed": res.changed,
                "dedup_deleted_src": bool(getattr(res, "dedup_deleted_src", False)),
                "note_path": str(note_path) if note_path else None,
            },
        )

        _log(paths, f"OK: {sj.name} -> {res.dst}")

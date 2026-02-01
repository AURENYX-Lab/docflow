# src/docflow/__main__.py
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from docflow.core.config import AppConfig
from docflow.ocr.preflight import run_preflight, PreflightError

from docflow.suggest.pipeline import run_suggest_batch, SuggestPaths, SuggestOptions
from docflow.apply.pipeline import run_apply_batch, ApplyPaths, ApplyOptions
from docflow.ocr.pipeline import run_ocr_inbox, OCRPaths, OCRRunOptions


def _p(v: Optional[str]) -> Optional[Path]:
    if v is None:
        return None
    return Path(v).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="docflow")

    # globale Overrides (optional)
    p.add_argument("--archiv-root", type=str, default=None)
    p.add_argument("--inbox-dir", type=str, default=None)
    p.add_argument("--settings-dir", type=str, default=None)
    p.add_argument("--ollama-model", type=str, default=None)
    p.add_argument("--ollama-timeout-s", type=int, default=None)
    p.add_argument("--ollama-bin", type=str, default=None)

    p.add_argument("--dry-run", action="store_true")

    sub = p.add_subparsers(dest="cmd", required=True)

    # OCR
    o = sub.add_parser("ocr")
    o.add_argument("--force", action="store_true")
    o.add_argument("--limit", type=int, default=0)
    o.add_argument("--copy", action="store_true")
    o.add_argument("--no-preflight", action="store_true")

    # suggest
    s = sub.add_parser("suggest")
    s.add_argument("--force", action="store_true")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--no-llm", action="store_true")

    # apply
    a = sub.add_parser("apply")
    a.add_argument("--force", action="store_true")
    a.add_argument("--limit", type=int, default=0)
    a.add_argument("--move", action="store_true")

    # preflight
    pf = sub.add_parser("preflight")
    pf.add_argument("--strict", action="store_true")

    return p


def main() -> None:
    args = build_parser().parse_args()

    cfg = AppConfig.load(
        archiv_root=_p(args.archiv_root),
        inbox_dir=_p(args.inbox_dir),
        settings_dir=_p(args.settings_dir),
        ollama_model=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout_s,
        ollama_bin=args.ollama_bin,
    )
    cfg.ensure_dirs()

    if args.cmd == "preflight":
        try:
            run_preflight(strict=bool(args.strict))
            print("preflight: ok")
        except PreflightError as e:
            raise SystemExit(str(e)) from e
            print(f"preflight: FAIL: {e}", file=sys.stderr)
        return

    if args.cmd == "ocr":
        if not args.no_preflight:
            run_preflight(strict=True)

        run_ocr_inbox(
            cfg=cfg,
            paths=OCRPaths(
                inbox_dir=cfg.paths.inbox_dir,
                log_dir=cfg.paths.log_dir,
                quarantine_dir=cfg.paths.quarantine_dir,
            ),
            options=OCRRunOptions(
                dry_run=bool(args.dry_run),
                limit=int(args.limit),
                force=bool(args.force),
                copy_instead_of_replace=bool(args.copy),
            ),
        )
        return

    if args.cmd == "suggest":
        run_suggest_batch(
            cfg=cfg,
            paths=SuggestPaths(
                inbox_dir=cfg.paths.inbox_dir,
                out_dir=cfg.paths.inbox_dir / "_suggestions",
                log_dir=cfg.paths.log_dir,
            ),
            options=SuggestOptions(
                dry_run=bool(args.dry_run),
                limit=int(args.limit),
                force=bool(args.force),
                use_llm=not bool(args.no_llm),
            ),
        )
        return

    if args.cmd == "apply":
        run_apply_batch(
            cfg=cfg,
            paths=ApplyPaths(
                suggestions_dir=cfg.paths.inbox_dir / "_suggestions",
                log_dir=cfg.paths.log_dir,
            ),
            options=ApplyOptions(
                dry_run=bool(args.dry_run),
                limit=int(args.limit),
                force=bool(args.force),
                mode=("move" if bool(args.move) else "copy"),
            ),
        )
        return

    raise SystemExit(f"Unknown cmd: {args.cmd}")


if __name__ == "__main__":
    main()

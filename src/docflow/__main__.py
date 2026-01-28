from __future__ import annotations
import argparse
import json
from pathlib import Path

from .config import load_config
from .discovery import discover_areas, list_pdfs
from .extract import extract_text_budget
from .heuristics import extract_date, extract_aktenzeichen, guess_area, guess_frist
from .naming import make_suggested_filename, year_from_datum
from .schema import validate_doc, dumps_min
from .audit import sha256_file, sha256_text, utc_ts, append_manifest
from .ollama_client import Ollama
from .apply import apply_one


def build_prompt(areas: list[str], meta_seed: dict, text: str) -> str:
    # Model soll NICHT area/year/filename “neu erfinden”, sondern nur veredeln.
    return f"""
Du bist ein offline Dokumenten-Assistent. Du bekommst OCR-Text und eine Vorbelegung (seed).
Aufgabe:
- Ergänze/verbessere doc_title, summary (3-6 Sätze, keine sensiblen Details), key_points (3-8 kurze Punkte).
- Ergänze yaml.typ, yaml.quelle, yaml.status, yaml.tags (1-3 Tags), wenn sinnvoll.
- Ändere NICHT: suggested_area, suggested_year, yaml.datum, yaml.aktenzeichen, yaml.frist, suggested_filename.
- Gib exakt EIN MINIFIED JSON aus (eine Zeile), keine Codefences, kein Text davor/danach.
- Top-Level Keys nur: input_pdf,suggested_area,suggested_year,suggested_filename,doc_title,summary,key_points,yaml
- suggested_area ist CLOSED WORLD und MUSS eins von: {", ".join(areas)}

SEED_JSON:
{json.dumps(meta_seed, ensure_ascii=False)}

TEXT_BEGIN
{text}
TEXT_END
""".strip()


def suggest(cfg, force: bool, limit: int) -> int:
    areas = discover_areas(cfg.archiv_root)
    if not areas:
        raise SystemExit(f"Keine Area-Ordner gefunden in {cfg.archiv_root}")

    ollama = Ollama(cfg.ollama_host, cfg.ollama_model, cfg.ollama_keep_alive, cfg.ollama_timeout_s)
    ollama.warmup()

    pdfs = list_pdfs(cfg.inbox_dir)
    if not pdfs:
        print(f"Keine PDFs in {cfg.inbox_dir}")
        return 0

    done = 0
    for pdf in pdfs:
        stem = pdf.stem
        out_json = cfg.suggestions_dir / f"{stem}.json"
        raw_path = cfg.logs_dir / f"{stem}.ollama.raw.txt"

        if out_json.exists() and not force:
            continue
        if limit and done >= limit:
            break

        text = extract_text_budget(
            pdf,
            max_bytes=cfg.max_text_bytes,
            front_pages=cfg.front_pages,
            dist_pages=cfg.dist_pages,
            start_pct=cfg.dist_start_pct,
            end_pct=cfg.dist_end_pct,
        )
        if not text.strip():
            append_manifest(
                cfg.logs_dir,
                {
                    "ts_utc": utc_ts(),
                    "action": "SUGGEST_SKIP",
                    "input_pdf": str(pdf),
                    "reason": "no_text",
                    "sha256_pdf": sha256_file(pdf),
                },
            )
            continue

        # deterministic extraction (fast)
        datum = extract_date(text)
        aktenzeichen = extract_aktenzeichen(text)
        area = guess_area(text)
        frist = guess_frist(text, area, datum)

        year = year_from_datum(datum)
        status = "offen"
        quelle = None

        # make a conservative short descriptor seed; model will refine doc_title, not filename base
        kurz = "dokument"
        if "ablehnungsbescheid" in text.lower():
            kurz = "ablehnungsbescheid"
        elif "bescheid" in text.lower():
            kurz = "bescheid"
        elif "widerspruch" in text.lower():
            kurz = "widerspruch"

        suggested_filename = make_suggested_filename(datum, kurz, quelle, status)

        seed = {
            "input_pdf": str(pdf),
            "suggested_area": area,
            "suggested_year": year,
            "suggested_filename": suggested_filename,
            "doc_title": "",
            "summary": "",
            "key_points": [],
            "yaml": {
                "typ": None,
                "bereich": area,
                "datum": datum,
                "quelle": None,
                "aktenzeichen": aktenzeichen,
                "frist": frist,
                "status": status,
                "tags": [],
            },
        }

        prompt = build_prompt(areas, seed, text)

        # streaming raw writing => file gets content immediately
        buf = []
        raw_path.write_text("", encoding="utf-8")
        try:
            for chunk in ollama.generate_stream(prompt, options={"temperature": 0.1}):
                buf.append(chunk)
                raw_path.write_text("".join(buf), encoding="utf-8")
        except Exception as e:
            append_manifest(
                cfg.logs_dir,
                {
                    "ts_utc": utc_ts(),
                    "action": "SUGGEST_FAIL",
                    "input_pdf": str(pdf),
                    "error": str(e),
                    "sha256_pdf": sha256_file(pdf),
                    "sha256_text": sha256_text(text),
                },
            )
            continue

        raw = "".join(buf).strip()

        # If model violates, fall back to seed-only draft
        meta = None
        try:
            meta = json.loads(raw)
        except Exception:
            meta = seed

        # enforce invariants
        meta["input_pdf"] = str(pdf)
        meta["suggested_area"] = area
        meta["suggested_year"] = year
        meta["suggested_filename"] = suggested_filename
        meta.setdefault("yaml", {})
        meta["yaml"]["bereich"] = area
        meta["yaml"]["datum"] = datum
        meta["yaml"]["aktenzeichen"] = aktenzeichen
        meta["yaml"]["frist"] = frist
        meta["yaml"]["status"] = meta["yaml"].get("status") or status
        meta["yaml"]["tags"] = meta["yaml"].get("tags") or []

        # If title still empty, pick a safe fallback
        if not str(meta.get("doc_title") or "").strip():
            meta["doc_title"] = pdf.stem

        # Validate strict schema (top-level additionalProperties False)
        try:
            validate_doc(meta)
        except Exception:
            # if model gave extra keys, strip to allowed
            meta = {
                "input_pdf": meta.get("input_pdf", str(pdf)),
                "suggested_area": meta.get("suggested_area", area),
                "suggested_year": int(meta.get("suggested_year", year)),
                "suggested_filename": meta.get("suggested_filename", suggested_filename),
                "doc_title": meta.get("doc_title", pdf.stem),
                "summary": meta.get("summary", ""),
                "key_points": (
                    meta.get("key_points", []) if isinstance(meta.get("key_points"), list) else []
                ),
                "yaml": meta.get("yaml", seed["yaml"]),
            }
            validate_doc(meta)

        out_json.write_text(dumps_min(meta) + "\n", encoding="utf-8")

        append_manifest(
            cfg.logs_dir,
            {
                "ts_utc": utc_ts(),
                "action": "SUGGEST_OK",
                "input_pdf": str(pdf),
                "suggestion_json": str(out_json),
                "raw_path": str(raw_path),
                "sha256_pdf": sha256_file(pdf),
                "sha256_text": sha256_text(text),
                "area": area,
                "year": str(year),
                "suggested_filename": suggested_filename,
            },
        )

        done += 1
        print(f"[OK] {pdf.name} -> {out_json.name}")

    return done


def apply(cfg, move: bool, limit: int) -> int:
    jsons = sorted(cfg.suggestions_dir.glob("*.json"))
    if not jsons:
        print("Keine Suggestions vorhanden.")
        return 0

    done = 0
    for js in jsons:
        if limit and done >= limit:
            break
        meta = json.loads(js.read_text(encoding="utf-8"))

        # Re-extract small text again for text-sha audit (cheap); could also store in suggestion.
        pdf = Path(meta["input_pdf"])
        text = ""
        try:
            text = extract_text_budget(
                pdf,
                max_bytes=cfg.max_text_bytes,
                front_pages=cfg.front_pages,
                dist_pages=cfg.dist_pages,
                start_pct=cfg.dist_start_pct,
                end_pct=cfg.dist_end_pct,
            )
        except Exception:
            text = ""

        dest_pdf, note = apply_one(cfg, meta, text_used=text, move=move)
        print(f"[APPLY] {pdf.name} -> {dest_pdf}")
        if note:
            print(f"        note -> {note}")
        done += 1

    return done


def main():
    p = argparse.ArgumentParser(
        prog="docflow",
        description="OCR-PDFs klassifizieren, Vorschläge erzeugen, anwenden, auditieren.",
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Nichts kopieren/verschieben, nur planen/loggen."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("suggest", help="Erzeuge Suggestions (JSON + Raw + Manifest)")
    s.add_argument("--force", action="store_true", help="Überschreibe bestehende JSONs.")
    s.add_argument("--limit", type=int, default=0)

    a = sub.add_parser(
        "apply", help="Wende geprüfte Suggestions an (kopiere/verschiebe + Obsidian)"
    )
    a.add_argument(
        "--move",
        action="store_true",
        help="Input-PDFs aus INBOX nach Archiv verschieben statt kopieren.",
    )
    a.add_argument("--limit", type=int, default=0)

    args = p.parse_args()
    cfg = load_config(dry_run=args.dry_run)

    if args.cmd == "suggest":
        suggest(cfg, force=args.force, limit=args.limit)
    elif args.cmd == "apply":
        apply(cfg, move=args.move, limit=args.limit)


if __name__ == "__main__":
    main()

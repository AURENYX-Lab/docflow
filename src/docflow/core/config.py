from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    archiv_root: Path
    inbox_dir: Path
    suggestions_dir: Path
    logs_dir: Path
    applied_dir: Path

    obsidian_vault: Path | None
    obsidian_notes_root: str

    ollama_host: str
    ollama_model: str
    ollama_keep_alive: str
    ollama_timeout_s: int

    max_text_bytes: int
    front_pages: int
    dist_pages: int
    dist_start_pct: int
    dist_end_pct: int

    dry_run: bool


def load_config(dry_run: bool = False) -> Config:
    home = Path.home()

    archiv_root = Path(os.getenv("ARCHIV_ROOT", str(home / "Documents" / "ARCHIV"))).expanduser()
    inbox_dir = Path(os.getenv("INBOX_DIR", str(archiv_root / "99_TEMP_EINGANG"))).expanduser()

    suggestions_dir = inbox_dir / "_suggestions"
    logs_dir = inbox_dir / "_logs"
    applied_dir = inbox_dir / "_applied"

    obs_vault = os.getenv("OBSIDIAN_VAULT", "").strip()
    obsidian_vault = Path(obs_vault).expanduser() if obs_vault else None
    obsidian_notes_root = os.getenv("OBSIDIAN_NOTES_ROOT", "ARCHIV_NOTES").strip()

    cfg = Config(
        archiv_root=archiv_root,
        inbox_dir=inbox_dir,
        suggestions_dir=suggestions_dir,
        logs_dir=logs_dir,
        applied_dir=applied_dir,
        obsidian_vault=obsidian_vault,
        obsidian_notes_root=obsidian_notes_root,
        ollama_host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip(),
        ollama_model=os.getenv("MODEL", "llama3.1:8b-instruct-q4_K_M").strip(),
        ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip(),
        ollama_timeout_s=int(os.getenv("OLLAMA_TIMEOUT", "1800")),
        max_text_bytes=int(os.getenv("MAX_BYTES", "9000")),
        front_pages=int(os.getenv("FRONT_PAGES", "3")),
        dist_pages=int(os.getenv("DIST_PAGES", "1")),
        dist_start_pct=int(os.getenv("DIST_START_PCT", "20")),
        dist_end_pct=int(os.getenv("DIST_END_PCT", "90")),
        dry_run=dry_run,
    )

    # Ensure dirs exist
    cfg.suggestions_dir.mkdir(parents=True, exist_ok=True)
    cfg.logs_dir.mkdir(parents=True, exist_ok=True)
    cfg.applied_dir.mkdir(parents=True, exist_ok=True)

    return cfg

# docflow/src/docflow/apply/obsidian.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from docflow.apply.filesystem import atomic_write_text, resolve_collision
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docflow.settings import Settings


class ObsidianError(RuntimeError):
    pass


def _yaml_escape(s: str) -> str:
    # safe enough for short strings; deterministic
    s = (s or "").replace("\n", " ").strip()
    if s == "":
        return '""'
    if any(ch in s for ch in [":", "#", "{", "}", "[", "]", ",", '"', "'"]):
        return '"' + s.replace('"', '\\"') + '"'
    return s


@dataclass(frozen=True)
class NotePolicy:
    vault_root: Path
    notes_dir: Path
    include_frontmatter: bool
    link_style: str  # "relative" | "absolute"
    file_name_mode: str  # "pdf_name" | "title"

    @staticmethod
    def from_settings(settings: Settings) -> "NotePolicy":
        # Settings are already validated by Pydantic loader.
        ap = settings.pipeline.apply
        obs = ap.obsidian
        if obs is None:
            raise ObsidianError(
                "pipeline.apply.obsidian missing (required when pipeline.apply.write_obsidian_note=true)"
            )

        vault_root = Path(str(obs.vault_root)).expanduser().resolve()
        notes_dir_raw = Path(str(obs.notes_dir)).expanduser()

        include_frontmatter = bool(getattr(obs, "include_frontmatter", True))
        link_style = str(getattr(obs, "link_style", "relative"))
        file_name_mode = str(getattr(obs, "file_name_mode", "pdf_name"))

        if link_style not in ("relative", "absolute"):
            raise ObsidianError("apply.obsidian.link_style must be 'relative' or 'absolute'")
        if file_name_mode not in ("pdf_name", "title"):
            raise ObsidianError("apply.obsidian.file_name_mode must be 'pdf_name' or 'title'")

        # notes_dir can be absolute or relative to vault_root
        nd = notes_dir_raw if notes_dir_raw.is_absolute() else (vault_root / notes_dir_raw)

        return NotePolicy(
            vault_root=vault_root,
            notes_dir=nd.resolve(),
            include_frontmatter=include_frontmatter,
            link_style=link_style,
            file_name_mode=file_name_mode,
        )


def _note_filename(policy: NotePolicy, suggestion: Dict[str, Any], archived_pdf_path: Path) -> str:
    if policy.file_name_mode == "pdf_name":
        return archived_pdf_path.with_suffix(".md").name

    title = str(suggestion.get("doc_title") or "Dokument").strip()

    # conservative slug
    safe = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in title)
    safe = "_".join(safe.split()).strip("_")[:120] or "Dokument"
    return f"{safe}.md"


def _link(policy: NotePolicy, target: Path) -> str:
    if policy.link_style == "absolute":
        return str(target)

    # relative to vault root if possible; else absolute string
    try:
        rel = target.relative_to(policy.vault_root)
        return str(rel)
    except Exception:
        return str(target)


def render_note_markdown(
    *,
    policy: NotePolicy,
    suggestion: Dict[str, Any],
    archived_pdf_path: Path,
    archived_pdf_sha256: str,
    suggestion_json_path: Path,
    settings_sha256: str,
) -> str:
    y = suggestion.get("yaml") if isinstance(suggestion.get("yaml"), dict) else {}
    tags = y.get("tags") if isinstance(y.get("tags"), list) else []

    fm_lines: List[str] = []
    if policy.include_frontmatter:
        fm_lines.append("---")
        fm_lines.append(f"title: {_yaml_escape(str(suggestion.get('doc_title') or 'Dokument'))}")
        fm_lines.append(
            f"bereich: {_yaml_escape(str(y.get('bereich') or suggestion.get('suggested_area') or ''))}"
        )
        fm_lines.append(f"datum: {_yaml_escape(str(y.get('datum') or ''))}")
        fm_lines.append(f"quelle: {_yaml_escape(str(y.get('quelle') or ''))}")
        fm_lines.append(f"status: {_yaml_escape(str(y.get('status') or ''))}")
        fm_lines.append(
            f"aktenzeichen: {y.get('aktenzeichen') if isinstance(y.get('aktenzeichen'), list) else []}"
        )
        fm_lines.append(f"frist: {_yaml_escape(str(y.get('frist') or ''))}")
        fm_lines.append(f"sha256: {_yaml_escape(archived_pdf_sha256)}")
        fm_lines.append(f"suggestion_json: {_yaml_escape(_link(policy, suggestion_json_path))}")
        fm_lines.append(f"settings_sha256: {_yaml_escape(settings_sha256)}")
        fm_lines.append(f"tags: {tags if isinstance(tags, list) else []}")
        fm_lines.append("---\n")

    link = _link(policy, archived_pdf_path)

    md: List[str] = []
    md.extend(fm_lines)
    md.append(f"# {suggestion.get('doc_title') or 'Dokument'}\n")
    md.append(f"**PDF:** `{link}`\n")
    md.append(f"**SHA256:** `{archived_pdf_sha256}`\n")

    summary = str(suggestion.get("summary") or "—").strip()
    md.append("## Zusammenfassung\n")
    md.append(summary + "\n")

    kps = suggestion.get("key_points")
    if isinstance(kps, list) and kps:
        md.append("## Key Points\n")
        for kp in kps[:12]:
            if isinstance(kp, str) and kp.strip():
                md.append(f"- {kp.strip()}")
        md.append("")

    md.append("## Metadaten\n")
    md.append(f"- Bereich: `{y.get('bereich')}`")
    md.append(f"- Datum: `{y.get('datum')}`")
    md.append(f"- Quelle: `{y.get('quelle')}`")
    md.append(f"- Status: `{y.get('status')}`")
    md.append(f"- Aktenzeichen: `{y.get('aktenzeichen')}`")
    md.append(f"- Frist: `{y.get('frist')}`")
    md.append("")

    return "\n".join(md).rstrip() + "\n"


def write_note(
    *,
    policy: NotePolicy,
    suggestion: Dict[str, Any],
    archived_pdf_path: Path,
    archived_pdf_sha256: str,
    suggestion_json_path: Path,
    settings_sha256: str,
) -> Path:
    policy.notes_dir.mkdir(parents=True, exist_ok=True)
    fname = _note_filename(policy, suggestion, archived_pdf_path)
    out = policy.notes_dir / fname

    # Only needed for title-based naming, but harmless if you want it always.
    if out.exists() and policy.file_name_mode == "title":
        out = resolve_collision(out)

    md = render_note_markdown(
        policy=policy,
        suggestion=suggestion,
        archived_pdf_path=archived_pdf_path,
        archived_pdf_sha256=archived_pdf_sha256,
        suggestion_json_path=suggestion_json_path,
        settings_sha256=settings_sha256,
    )
    atomic_write_text(out, md, encoding="utf-8")
    return out

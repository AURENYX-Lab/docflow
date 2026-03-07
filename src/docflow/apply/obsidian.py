# docflow/src/docflow/apply/obsidian.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from docflow.apply.filesystem import atomic_write_text, resolve_collision

if TYPE_CHECKING:
    from docflow.settings import Settings


class ObsidianError(RuntimeError):
    pass


def _normalize_scalar(value: Any) -> str:
    """Normalize scalar-like values for stable markdown/frontmatter output."""
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize a list-like input into a deterministic list[str]."""
    if not isinstance(value, list):
        return []

    out: list[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            out.append(s)
    return out


def _display_list(values: list[str]) -> str:
    """Render list values for human-readable markdown."""
    return ", ".join(values) if values else "—"


@dataclass(frozen=True)
class NotePolicy:
    vault_root: Path
    notes_dir: Path
    include_frontmatter: bool
    link_style: str  # "relative" | "absolute"
    file_name_mode: str  # "pdf_name" | "title"

    @staticmethod
    def from_settings(settings: Settings) -> "NotePolicy":
        # Settings are already validated by the Pydantic loader.
        ap = settings.pipeline.apply
        obs = ap.obsidian
        if obs is None:
            raise ObsidianError(
                "pipeline.apply.obsidian missing "
                "(required when pipeline.apply.write_obsidian_note=true)"
            )

        vault_root = Path(str(obs.vault_root)).expanduser().resolve()
        notes_dir_raw = Path(str(obs.notes_dir)).expanduser()

        include_frontmatter = bool(getattr(obs, "include_frontmatter", True))
        link_style = str(getattr(obs, "link_style", "relative"))
        file_name_mode = str(getattr(obs, "file_name_mode", "pdf_name"))

        if link_style not in ("relative", "absolute"):
            raise ObsidianError(
                "apply.obsidian.link_style must be 'relative' or 'absolute'"
            )
        if file_name_mode not in ("pdf_name", "title"):
            raise ObsidianError(
                "apply.obsidian.file_name_mode must be 'pdf_name' or 'title'"
            )

        notes_dir = (
            notes_dir_raw
            if notes_dir_raw.is_absolute()
            else (vault_root / notes_dir_raw)
        )

        return NotePolicy(
            vault_root=vault_root,
            notes_dir=notes_dir.resolve(),
            include_frontmatter=include_frontmatter,
            link_style=link_style,
            file_name_mode=file_name_mode,
        )


def _note_filename(
    policy: NotePolicy,
    suggestion: dict[str, Any],
    archived_pdf_path: Path,
) -> str:
    if policy.file_name_mode == "pdf_name":
        return archived_pdf_path.with_suffix(".md").name

    title = _normalize_scalar(suggestion.get("doc_title")) or "Dokument"

    safe = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in title)
    safe = "_".join(safe.split()).strip("_")[:120] or "Dokument"
    return f"{safe}.md"


def _link(policy: NotePolicy, target: Path) -> str:
    if policy.link_style == "absolute":
        return str(target)

    try:
        rel = target.relative_to(policy.vault_root)
        return str(rel)
    except ValueError:
        return str(target)


def _build_frontmatter(
    *,
    suggestion: dict[str, Any],
    archived_pdf_sha256: str,
    suggestion_json_path: Path,
    settings_sha256: str,
    policy: NotePolicy,
) -> dict[str, Any]:
    y = suggestion.get("yaml") if isinstance(suggestion.get("yaml"), dict) else {}

    aktenzeichen = _normalize_string_list(y.get("aktenzeichen"))
    tags = _normalize_string_list(y.get("tags"))

    return {
        "title": _normalize_scalar(suggestion.get("doc_title")) or "Dokument",
        "bereich": _normalize_scalar(
            y.get("bereich") or suggestion.get("suggested_area")
        ),
        "datum": _normalize_scalar(y.get("datum")),
        "quelle": _normalize_scalar(y.get("quelle")),
        "status": _normalize_scalar(y.get("status")),
        "aktenzeichen": aktenzeichen,
        "frist": _normalize_scalar(y.get("frist")),
        "sha256": _normalize_scalar(archived_pdf_sha256),
        "suggestion_json": _normalize_scalar(_link(policy, suggestion_json_path)),
        "settings_sha256": _normalize_scalar(settings_sha256),
        "tags": tags,
    }


def _render_yaml_frontmatter(frontmatter: dict[str, Any]) -> str:
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return f"---\n{yaml_text}---\n"


def render_note_markdown(
    *,
    policy: NotePolicy,
    suggestion: dict[str, Any],
    archived_pdf_path: Path,
    archived_pdf_sha256: str,
    suggestion_json_path: Path,
    settings_sha256: str,
) -> str:
    y = suggestion.get("yaml") if isinstance(suggestion.get("yaml"), dict) else {}

    title = _normalize_scalar(suggestion.get("doc_title")) or "Dokument"
    summary = _normalize_scalar(suggestion.get("summary")) or "—"
    key_points = suggestion.get("key_points")
    aktenzeichen = _normalize_string_list(y.get("aktenzeichen"))

    lines: list[str] = []

    if policy.include_frontmatter:
        frontmatter = _build_frontmatter(
            suggestion=suggestion,
            archived_pdf_sha256=archived_pdf_sha256,
            suggestion_json_path=suggestion_json_path,
            settings_sha256=settings_sha256,
            policy=policy,
        )
        lines.append(_render_yaml_frontmatter(frontmatter).rstrip())
        lines.append("")

    pdf_link = _link(policy, archived_pdf_path)

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**PDF:** `{pdf_link}`")
    lines.append(f"**SHA256:** `{archived_pdf_sha256}`")
    lines.append("")
    lines.append("## Zusammenfassung")
    lines.append("")
    lines.append(summary)
    lines.append("")

    if isinstance(key_points, list):
        clean_points = [
            str(point).strip()
            for point in key_points[:12]
            if isinstance(point, str) and point.strip()
        ]
        if clean_points:
            lines.append("## Key Points")
            lines.append("")
            for point in clean_points:
                lines.append(f"- {point}")
            lines.append("")

    lines.append("## Metadaten")
    lines.append("")
    lines.append(
        f"- Bereich: `{_normalize_scalar(y.get('bereich') or suggestion.get('suggested_area'))}`"
    )
    lines.append(f"- Datum: `{_normalize_scalar(y.get('datum'))}`")
    lines.append(f"- Quelle: `{_normalize_scalar(y.get('quelle'))}`")
    lines.append(f"- Status: `{_normalize_scalar(y.get('status'))}`")
    lines.append(f"- Aktenzeichen: {_display_list(aktenzeichen)}")
    lines.append(f"- Frist: `{_normalize_scalar(y.get('frist'))}`")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_note(
    *,
    policy: NotePolicy,
    suggestion: dict[str, Any],
    archived_pdf_path: Path,
    archived_pdf_sha256: str,
    suggestion_json_path: Path,
    settings_sha256: str,
) -> Path:
    policy.notes_dir.mkdir(parents=True, exist_ok=True)

    filename = _note_filename(policy, suggestion, archived_pdf_path)
    out = policy.notes_dir / filename

    if out.exists() and policy.file_name_mode == "title":
        out = resolve_collision(out)

    markdown = render_note_markdown(
        policy=policy,
        suggestion=suggestion,
        archived_pdf_path=archived_pdf_path,
        archived_pdf_sha256=archived_pdf_sha256,
        suggestion_json_path=suggestion_json_path,
        settings_sha256=settings_sha256,
    )
    atomic_write_text(out, markdown, encoding="utf-8")
    return out

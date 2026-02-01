# docflow/src/docflow/apply/filesystem.py
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from docflow.core.audit import sha256_file


class FileOpError(RuntimeError):
    pass


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding)
    os.replace(tmp, path)


def _atomic_copy2_with_hash(src: Path, dst: Path, src_hash: str) -> str:
    """
    Copy src -> dst atomically:
      copy2 to dst.tmp (same dir), verify hash, then os.replace(tmp, dst).
    Returns dst sha256.
    """
    ensure_dir(dst.parent)

    tmp = dst.with_suffix(dst.suffix + ".tmp")

    # Clean stale tmp
    if tmp.exists():
        tmp.unlink()

    # Copy into tmp first
    shutil.copy2(src, tmp)

    # Verify hash BEFORE committing
    tmp_hash = sha256_file(tmp)
    if tmp_hash != src_hash:
        try:
            tmp.unlink()
        except Exception:
            pass
        raise FileOpError("Hash mismatch after atomic copy (tmp != src)")

    # Atomic commit
    os.replace(tmp, dst)
    return tmp_hash


def _samefile(a: Path, b: Path) -> bool:
    try:
        return a.samefile(b)
    except Exception:
        return False


def _collision_suffix(dst: Path, n: int) -> Path:
    # filename__01.pdf
    stem = dst.stem
    suf = dst.suffix
    return dst.with_name(f"{stem}__{n:02d}{suf}")


def resolve_collision(dst: Path, *, max_tries: int = 99) -> Path:
    if not dst.exists():
        return dst
    for i in range(1, max_tries + 1):
        cand = _collision_suffix(dst, i)
        if not cand.exists():
            return cand
    raise FileOpError(f"Too many collisions for: {dst.name}")


@dataclass(frozen=True)
class CopyMoveResult:
    src: Path
    dst: Path
    src_sha256: str
    dst_sha256: str
    changed: bool  # whether a new file was written/moved
    dedup_deleted_src: bool = False  # only true for skip_if_same + move


def copy_or_move_pdf(
    *,
    src: Path,
    dst: Path,
    mode: str,  # "copy" | "move"
    collision: str,  # "fail" | "suffix" | "skip_if_same"
) -> CopyMoveResult:
    if mode not in ("copy", "move"):
        raise FileOpError("mode must be 'copy' or 'move'")
    if collision not in ("fail", "suffix", "skip_if_same"):
        raise FileOpError("collision must be 'fail' | 'suffix' | 'skip_if_same'")

    if not src.exists() or not src.is_file():
        raise FileOpError(f"Source missing: {src}")
    ensure_dir(dst.parent)

    src_hash = sha256_file(src)

    # If dst exists, decide policy
    final_dst = dst
    if final_dst.exists():
        if collision == "skip_if_same":
            dst_hash = sha256_file(final_dst)
            if dst_hash == src_hash:
                # Dedup-move: destination already contains identical bytes; delete source.
                if mode == "move":
                    try:
                        src.unlink()
                    except Exception as e:
                        raise FileOpError(
                            f"Dedup delete failed for source: {src} ({type(e).__name__}: {e})"
                        )
                    return CopyMoveResult(
                        src=src,
                        dst=final_dst,
                        src_sha256=src_hash,
                        dst_sha256=dst_hash,
                        changed=False,
                        dedup_deleted_src=True,
                    )

                # copy + skip_if_same: no-op
                return CopyMoveResult(
                    src=src,
                    dst=final_dst,
                    src_sha256=src_hash,
                    dst_sha256=dst_hash,
                    changed=False,
                    dedup_deleted_src=False,
                )

            raise FileOpError(f"Destination exists (not same hash): {final_dst}")

        if collision == "suffix":
            final_dst = resolve_collision(final_dst)
        else:
            raise FileOpError(f"Destination exists: {final_dst}")

    # Write operation
    if mode == "copy":
        dst_hash = _atomic_copy2_with_hash(src, final_dst, src_hash)
        return CopyMoveResult(
            src=src,
            dst=final_dst,
            src_sha256=src_hash,
            dst_sha256=dst_hash,
            changed=True,
        )

    # move
    try:
        os.replace(src, final_dst)
    except OSError:
        shutil.move(str(src), str(final_dst))

    dst_hash = sha256_file(final_dst)
    if dst_hash != src_hash:
        raise FileOpError("Hash mismatch after move (unexpected)")
    return CopyMoveResult(
        src=src,
        dst=final_dst,
        src_sha256=src_hash,
        dst_sha256=dst_hash,
        changed=True,
    )

from __future__ import annotations

import errno
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import fcntl  # unix only
except Exception:  # pragma: no cover
    fcntl = None  # type: ignore


class AuditError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, data.encode(encoding))


def _append_line_locked(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass
        f.write(line)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
        if fcntl is not None:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    _append_line_locked(path, line)


@dataclass(frozen=True)
class AuditLogger:
    """
    Append-only audit log (JSONL).
    Designed for chain-of-custody:
    - records hashes before/after
    - includes settings_sha256 to guarantee reproducibility
    """

    manifest_path: Path
    settings_sha256: str

    def event(
        self,
        *,
        kind: str,
        input_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kind": kind,
            "settings_sha256": self.settings_sha256,
        }
        if input_path is not None:
            payload["input_path"] = str(input_path)
            if input_path.exists() and input_path.is_file():
                payload["input_sha256"] = sha256_file(input_path)
        if output_path is not None:
            payload["output_path"] = str(output_path)
            if output_path.exists() and output_path.is_file():
                payload["output_sha256"] = sha256_file(output_path)
        if meta:
            payload["meta"] = meta

        append_jsonl(self.manifest_path, payload)

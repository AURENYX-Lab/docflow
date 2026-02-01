# docflow/src/docflow/suggest/ollama_client.py
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


@dataclass(frozen=True)
class OllamaResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


class OllamaClientError(RuntimeError):
    pass


class OllamaClient:
    """
    Subprocess wrapper around `ollama run`.
    - strict separation of stdout/stderr
    - strips ANSI junk
    - supports timeouts
    """

    def __init__(self, *, model: str, timeout_s: int = 1800, env: Optional[Dict[str, str]] = None):
        self.model = model
        self.timeout_s = timeout_s
        self.env = env or {}

    def run(self, prompt: str) -> OllamaResult:
        cmd = ["ollama", "run", self.model]
        env = os.environ.copy()
        # reduce noise / history
        env["OLLAMA_NOHISTORY"] = "1"
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        env.update(self.env)

        try:
            proc = subprocess.run(
                cmd,
                input=prompt.encode("utf-8", errors="ignore"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=self.timeout_s,
                check=False,
            )
            out = strip_ansi(proc.stdout.decode("utf-8", errors="ignore")).strip()
            err = strip_ansi(proc.stderr.decode("utf-8", errors="ignore")).strip()
            return OllamaResult(
                ok=(proc.returncode == 0), stdout=out, stderr=err, returncode=proc.returncode
            )
        except subprocess.TimeoutExpired as e:
            out = strip_ansi((e.stdout or b"").decode("utf-8", errors="ignore")).strip()
            err = strip_ansi((e.stderr or b"").decode("utf-8", errors="ignore")).strip()
            return OllamaResult(ok=False, stdout=out, stderr=err, returncode=124, timed_out=True)
        except FileNotFoundError as e:
            raise OllamaClientError("ollama not found in PATH") from e

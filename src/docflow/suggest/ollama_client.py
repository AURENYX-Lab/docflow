from __future__ import annotations
from dataclasses import dataclass
import json
import requests
from typing import Iterator


@dataclass(frozen=True)
class Ollama:
    host: str
    model: str
    keep_alive: str
    timeout_s: int

    def warmup(self) -> None:
        # tiny call to ensure model is loaded
        payload = {
            "model": self.model,
            "prompt": "OK",
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0.0, "num_predict": 1},
        }
        try:
            requests.post(f"{self.host}/api/generate", json=payload, timeout=15).raise_for_status()
        except Exception:
            # warmup is best-effort
            pass

    def generate_stream(self, prompt: str, options: dict | None = None) -> Iterator[str]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": options or {"temperature": 0.1},
        }
        with requests.post(
            f"{self.host}/api/generate", json=payload, stream=True, timeout=self.timeout_s
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                j = json.loads(line)
                if "response" in j and j["response"]:
                    yield j["response"]
                if j.get("done") is True:
                    break

    def generate_text(self, prompt: str, options: dict | None = None) -> str:
        out = []
        for chunk in self.generate_stream(prompt, options=options):
            out.append(chunk)
        return "".join(out)

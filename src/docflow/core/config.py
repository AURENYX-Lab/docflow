# docflow/src/docflow/core/config.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from docflow.settings import Settings, SettingsPaths, load_settings


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppPaths:
    archiv_root: Path
    inbox_dir: Path
    log_dir: Path
    quarantine_dir: Path
    manifests_dir: Path

    def ensure_dirs(self) -> None:
        self.archiv_root.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.manifests_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class LLMConfig:
    ollama_model: str
    ollama_timeout_s: int
    ollama_bin: str


@dataclass(frozen=True)
class AppConfig:
    paths: AppPaths
    settings: Settings
    llm: LLMConfig

    year_dir_pattern: re.Pattern[str] = re.compile(r"^(19|20)\d{2}$")

    @staticmethod
    def load(
        *,
        archiv_root: Optional[Path] = None,
        inbox_dir: Optional[Path] = None,
        settings_dir: Optional[Path] = None,
        ollama_model: Optional[str] = None,
        ollama_timeout_s: Optional[int] = None,
        ollama_bin: Optional[str] = None,
    ) -> "AppConfig":
        home = Path.home()

        ar = (
            (archiv_root or Path(os.environ.get("ARCHIV_ROOT", home / "Documents" / "ARCHIV")))
            .expanduser()
            .resolve()
        )
        ib = (
            (inbox_dir or Path(os.environ.get("INBOX_DIR", ar / "99_TEMP_EINGANG")))
            .expanduser()
            .resolve()
        )

        log_dir = Path(os.environ.get("DOCFLOW_LOG_DIR", ib / "_logs")).expanduser().resolve()
        quar_dir = (
            Path(os.environ.get("DOCFLOW_QUAR_DIR", ib / "_quarantine")).expanduser().resolve()
        )
        manifests_dir = (
            Path(os.environ.get("DOCFLOW_MANIFESTS_DIR", ib / "_manifests")).expanduser().resolve()
        )

        sd_env = os.environ.get("DOCFLOW_SETTINGS_DIR")
        sd = settings_dir or (Path(sd_env) if sd_env else None)
        if sd is None:
            sd = Path(__file__).resolve().parents[1] / "settings"
        sd = sd.expanduser().resolve()

        # YAML Pflicht, Loader validiert alles
        paths_obj = SettingsPaths(settings_dir=sd)
        settings = load_settings(sd, paths_obj)

        model = ollama_model or os.environ.get(
            "DOCFLOW_OLLAMA_MODEL", "llama3.1:8b-instruct-q4_K_M"
        )
        timeout = (
            ollama_timeout_s
            if ollama_timeout_s is not None
            else int(os.environ.get("DOCFLOW_OLLAMA_TIMEOUT_S", "1800"))
        )
        binpath = ollama_bin or os.environ.get("DOCFLOW_OLLAMA_BIN", "ollama")

        paths = AppPaths(
            archiv_root=ar,
            inbox_dir=ib,
            log_dir=log_dir,
            quarantine_dir=quar_dir,
            manifests_dir=manifests_dir,
        )

        llm = LLMConfig(ollama_model=model, ollama_timeout_s=timeout, ollama_bin=binpath)

        return AppConfig(paths=paths, settings=settings, llm=llm)

    def ensure_dirs(self) -> None:
        self.paths.ensure_dirs()

    def allowed_area_ids(self) -> list[str]:
        return self.settings.allowed_area_ids()

    def validate_area_id(self, area_id: str) -> None:
        allowed = set(self.allowed_area_ids())
        if area_id not in allowed:
            raise ConfigError(f"Unknown area_id '{area_id}'. Allowed: {sorted(allowed)}")


# ✅ CLI-kompatibler Wrapper (damit __main__.py nicht dauernd bricht)
def load_config(*, dry_run: bool = False) -> AppConfig:
    cfg = AppConfig.load()
    cfg.ensure_dirs()
    return cfg

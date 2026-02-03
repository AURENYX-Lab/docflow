from __future__ import annotations

from pathlib import Path

from docflow.settings.defaults import load_settings
from docflow.settings.models import SettingsPaths


def _paths(settings_dir: Path) -> SettingsPaths:
    return SettingsPaths(settings_dir=str(settings_dir))


def test_settings_sha256_stable_for_same_files(tmp_settings_dir, tmp_path):
    s1 = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    s2 = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    assert s1.settings_sha256 == s2.settings_sha256


def test_settings_sha256_changes_when_any_required_file_changes(tmp_settings_dir, tmp_path):
    s1 = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    h1 = s1.settings_sha256

    # ändere 1 Byte deterministisch
    f = tmp_settings_dir / "heuristics.yaml"
    f.write_text(f.read_text(encoding="utf-8") + "\n# mutation\n", encoding="utf-8")

    s2 = load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    h2 = s2.settings_sha256

    assert h1 != h2, "settings_sha256 must change when a REQUIRED_FILE changes"

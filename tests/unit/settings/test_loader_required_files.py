from __future__ import annotations

from pathlib import Path
import pytest

from docflow.settings.defaults import load_settings, SettingsError
from docflow.settings.models import SettingsPaths


def _paths(settings_dir: Path) -> SettingsPaths:
    return SettingsPaths(settings_dir=str(settings_dir))


def test_load_settings_missing_required_files_hard_fail(tmp_path: Path):
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()

    # absichtlich nur eine Datei
    (settings_dir / "categories.yaml").write_text(
        "closed_world: true\nareas: []\n", encoding="utf-8"
    )

    with pytest.raises(SettingsError) as e:
        load_settings(settings_dir, _paths(tmp_path))

    assert "Missing required settings files" in str(e.value)

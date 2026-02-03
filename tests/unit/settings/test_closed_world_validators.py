from __future__ import annotations

import pytest

from docflow.settings.defaults import load_settings, SettingsError
from docflow.settings.models import SettingsPaths


def _paths(settings_dir: Path) -> SettingsPaths:
    return SettingsPaths(settings_dir=str(settings_dir))


def test_categories_closed_world_false_fails(tmp_settings_dir, tmp_path):
    p = tmp_settings_dir / "categories.yaml"
    txt = p.read_text(encoding="utf-8")
    # brutal: ersetze true -> false (falls vorhanden)
    if "closed_world: true" in txt:
        p.write_text(txt.replace("closed_world: true", "closed_world: false"), encoding="utf-8")
    else:
        # falls nicht vorhanden: prepend false
        p.write_text("closed_world: false\n" + txt, encoding="utf-8")

    with pytest.raises(SettingsError) as e:
        load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    assert "closed_world" in str(e.value).lower()


def test_categories_closed_world_missing_fails(tmp_settings_dir, tmp_path):
    p = tmp_settings_dir / "categories.yaml"
    lines = p.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.strip().startswith("closed_world:")]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(SettingsError) as e:
        load_settings(tmp_settings_dir, _paths(tmp_settings_dir))
    assert "closed_world" in str(e.value).lower()

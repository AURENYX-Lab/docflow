from __future__ import annotations

import os
import subprocess
import sys
import pytest


@pytest.mark.integration
def test_cli_help_never_crashes(run_integration: bool):
    if not run_integration:
        pytest.skip("set RUN_INTEGRATION=1 to run integration tests")

    cp = subprocess.run([sys.executable, "-m", "docflow", "--help"], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr


@pytest.mark.integration
def test_cli_unknown_command_exits_nonzero(run_integration: bool):
    if not run_integration:
        pytest.skip("set RUN_INTEGRATION=1 to run integration tests")

    cp = subprocess.run(
        [sys.executable, "-m", "docflow", "no_such_cmd"], capture_output=True, text=True
    )
    assert cp.returncode != 0

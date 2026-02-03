from __future__ import annotations

import pytest

from docflow.cli.__main__ import build_parser


def test_cli_requires_subcommand() -> None:
    p = build_parser()
    with pytest.raises(SystemExit) as e:
        _ = p.parse_args([])
    # argparse uses exit code 2 for usage errors
    assert e.value.code == 2


def test_cli_parses_global_flags_before_cmd() -> None:
    p = build_parser()
    ns = p.parse_args(["--dry-run", "suggest"])
    assert ns.dry_run is True
    assert ns.cmd == "suggest"


def test_cli_unknown_subcommand_exits_2() -> None:
    p = build_parser()
    with pytest.raises(SystemExit) as e:
        _ = p.parse_args(["no_such_cmd"])
    assert e.value.code == 2

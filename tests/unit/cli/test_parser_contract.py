import pytest

from docflow.cli.__main__ import build_parser


def test_cli_build_parser_smoke() -> None:
    p = build_parser()
    assert p is not None
    # darf immer funktionieren (keine Settings laden, kein Crash)
    txt = p.format_help()
    assert "docflow" in txt.lower()


@pytest.mark.parametrize("cmd", ["preflight", "ocr", "suggest", "apply"])
def test_cli_subcommand_parses(cmd: str) -> None:
    p = build_parser()
    ns = p.parse_args([cmd])
    assert getattr(ns, "cmd") == cmd


def test_cli_unknown_arg_exits_2() -> None:
    p = build_parser()
    with pytest.raises(SystemExit) as e:
        p.parse_args(["--definitely-not-a-flag"])
    assert int(getattr(e.value, "code", 0)) == 2

from __future__ import annotations

import pytest

from docflow.suggest.jsonfix import JsonFixError, extract_and_parse_json


def test_jsonfix_extracts_first_balanced_json_ignoring_junk() -> None:
    junk = "\x1b[?25lspinner...\n>>> thinking\n"
    s = junk + "some preface\n" + '{"a": 1, "b": {"c": 2}}\n' + "more junk\n" + '{"a": 999}\n'
    res = extract_and_parse_json(s)
    assert res.ok is True, res.error
    assert res.obj["a"] == 1
    assert res.obj["b"]["c"] == 2


def test_jsonfix_rejects_when_no_json_object_found() -> None:
    res = extract_and_parse_json("no json here ...")
    assert res.ok is False
    assert "No JSON object found" in (res.error or "")

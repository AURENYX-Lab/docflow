from __future__ import annotations

from pathlib import Path
import pytest

from docflow.apply.filesystem import copy_or_move_pdf, FileOpError


PDF_A = b"%PDF-1.4\nA\n%%EOF\n"
PDF_B = b"%PDF-1.4\nB\n%%EOF\n"


def test_fileops_collision_fail_raises(tmp_path: Path):
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_bytes(PDF_A)
    dst.write_bytes(PDF_B)

    with pytest.raises(FileOpError) as e:
        copy_or_move_pdf(src=src, dst=dst, mode="copy", collision="fail")

    assert "Destination exists" in str(e.value)


def test_fileops_collision_suffix_creates_deterministic_suffix(tmp_path: Path):
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_bytes(PDF_A)
    dst.write_bytes(PDF_B)

    r1 = copy_or_move_pdf(src=src, dst=dst, mode="copy", collision="suffix")
    assert r1.dst.name == "dst__01.pdf"
    assert r1.dst.exists()

    # second run should create __02
    src2 = tmp_path / "src2.pdf"
    src2.write_bytes(PDF_A)
    r2 = copy_or_move_pdf(src=src2, dst=dst, mode="copy", collision="suffix")
    assert r2.dst.name == "dst__02.pdf"
    assert r2.dst.exists()


def test_fileops_collision_skip_if_same_no_write(tmp_path: Path):
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_bytes(PDF_A)
    dst.write_bytes(PDF_A)

    r = copy_or_move_pdf(src=src, dst=dst, mode="copy", collision="skip_if_same")
    assert r.changed is False
    assert src.exists(), "copy+skip_if_same must not delete source"


def test_fileops_skip_if_same_different_hash_raises(tmp_path: Path):
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    src.write_bytes(PDF_A)
    dst.write_bytes(PDF_B)

    with pytest.raises(FileOpError) as e:
        copy_or_move_pdf(src=src, dst=dst, mode="copy", collision="skip_if_same")

    assert "not same hash" in str(e.value)

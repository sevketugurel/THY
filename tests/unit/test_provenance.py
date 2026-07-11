"""Unit tests for src.data.provenance -- input-file identity stamping.

Every full-data run script logs which EXACT bytes it read (path + sha256),
not just a filename -- a filename alone doesn't prove the content wasn't
silently swapped (M5e, 2026-07-11: user asked for proof the v2 data source
was genuinely active, not a stale/wrong file at the same path).

marker: unit (solver-free, pure logic).
"""
import hashlib

import pytest

from src.data.provenance import file_provenance

pytestmark = pytest.mark.unit


def test_file_provenance_reports_correct_sha256(tmp_path):
    p = tmp_path / "sample.xlsx"
    p.write_bytes(b"hello world")
    expected = hashlib.sha256(b"hello world").hexdigest()

    result = file_provenance(p)
    assert result["sha256"] == expected


def test_file_provenance_reports_absolute_path(tmp_path):
    p = tmp_path / "sample.xlsx"
    p.write_bytes(b"data")

    result = file_provenance(p)
    assert result["path"] == str(p.resolve())


def test_file_provenance_reports_size_bytes(tmp_path):
    p = tmp_path / "sample.xlsx"
    p.write_bytes(b"0123456789")

    result = file_provenance(p)
    assert result["size_bytes"] == 10


def test_file_provenance_differs_for_different_content(tmp_path):
    p1 = tmp_path / "a.xlsx"
    p2 = tmp_path / "b.xlsx"
    p1.write_bytes(b"content A")
    p2.write_bytes(b"content B")

    assert file_provenance(p1)["sha256"] != file_provenance(p2)["sha256"]


def test_file_provenance_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        file_provenance(tmp_path / "does_not_exist.xlsx")

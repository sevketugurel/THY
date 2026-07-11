"""Unit tests for src.data.elapsed_parser.

Elapsed1/Elapsed2 (per-leg block time) cells in the v2 O&D file arrive as
TEXT strings ("DD.MM.1899 HH:MM:SS", an Excel 1899-epoch artifact) -- this
is the primary parse path, confirmed by direct inspection of the real file
(openpyxl data_type='s'). datetime.time/datetime/timedelta branches are
defensive (schema-safety against a different pandas/openpyxl engine
version), not exercised by the real v2 file.

wrap_corrected_journey_minutes composes the true multi-leg duration from
elapsed1 + gap + elapsed2, independent of the displayed "Gate-to-Gate"
field, which silently wraps mod 1440 for journeys >=24h (organizer-
confirmed bug; verified against the real file with zero exceptions across
57,317 rows -- see docs/decisions.md 2026-07-11 M5e entry).

marker: unit (solver-free, pure logic).
"""
import datetime

import pytest

from src.data.elapsed_parser import parse_elapsed_minutes, wrap_corrected_journey_minutes

pytestmark = pytest.mark.unit


def test_parses_real_v2_string_format():
    assert parse_elapsed_minutes("30.12.1899 06:19:00") == 379


def test_parses_string_defensively_regardless_of_epoch_day_prefix():
    assert parse_elapsed_minutes("31.12.1899 00:05:00") == 5


def test_parses_string_with_nonzero_seconds_truncates_like_minutes_helper():
    # Mirrors loaders._minutes' existing datetime.time convention (hour*60+minute,
    # seconds ignored) -- real v2 data never has nonzero seconds (verified), this
    # only pins defensive behavior if it ever did.
    assert parse_elapsed_minutes("30.12.1899 01:00:31") == 60


def test_parses_datetime_time_object():
    assert parse_elapsed_minutes(datetime.time(7, 35)) == 455


def test_parses_datetime_datetime_object_with_epoch_date():
    assert parse_elapsed_minutes(datetime.datetime(1899, 12, 30, 9, 5)) == 545


def test_parses_timedelta_object():
    assert parse_elapsed_minutes(datetime.timedelta(hours=2, minutes=15)) == 135


def test_raises_valueerror_on_unrecognized_string():
    with pytest.raises(ValueError):
        parse_elapsed_minutes("not a time")


def test_raises_typeerror_on_unsupported_type():
    with pytest.raises(TypeError):
        parse_elapsed_minutes(None)
    with pytest.raises(TypeError):
        parse_elapsed_minutes(42)


def test_wrap_corrected_journey_minutes_handles_real_multiday_journey():
    # TK EZE->IST->PEK, real row from the v2 O&D file (docs/decisions.md).
    # Displayed (wrapped) Gate-to-Gate for this row is 280min -- must NOT
    # collapse to that; true duration is 28h40m.
    assert wrap_corrected_journey_minutes(1020, 155, 545) == 1720


def test_wrap_corrected_journey_minutes_matches_short_journey_unchanged():
    # A <24h journey must equal simple elapsed1+gap+elapsed2 with no wrap.
    assert wrap_corrected_journey_minutes(120, 90, 150) == 360


def test_wrap_corrected_journey_minutes_rounds_fractional_gap():
    assert wrap_corrected_journey_minutes(120, 90.6, 150) == 361

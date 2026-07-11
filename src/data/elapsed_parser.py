"""Wrap-safe parsing for the v2 O&D file's ElapsedTime1/ElapsedTime2 columns.

Elapsed1/Elapsed2 are single-leg block-time durations -- structurally <24h
(a single flight leg is never a full day long; verified against the real
v2 file: max 23h45m/23h00m across all 57,317 rows for both columns), so
they never wrap. The displayed "Gate-to-Gate Uçuş Süresi" field, by
contrast, is a single Excel time-of-day cell representing the FULL
multi-leg journey and silently wraps mod 1440 once that total reaches
24h (organizer-confirmed bug). The true total is recoverable losslessly by
summing Elapsed1 + the (already wrap-safe, real pd.Timestamp-based)
connection gap + Elapsed2 -- see docs/decisions.md 2026-07-11 M5e entry
for the real-data proof (0/57,317 exceptions).
"""
import datetime


def parse_elapsed_minutes(value) -> int:
    """Parse one ElapsedTime1/ElapsedTime2 cell to integer minutes.

    Primary case (real v2 file): str "DD.MM.YYYY HH:MM:SS" (TEXT cell,
    openpyxl data_type='s') -- trailing HH:MM[:SS] parsed, date prefix
    (Excel 1899 epoch artifact) ignored. Defensive cases (schema-safety
    for a future data drop or different pandas/openpyxl engine version):
    datetime.time / datetime.datetime / pandas.Timestamp (.hour/.minute,
    same pattern as loaders._minutes) and datetime.timedelta
    (.total_seconds()/60). Raises ValueError on an unparseable string,
    TypeError on any other unsupported type.
    """
    if isinstance(value, str):
        try:
            _, time_part = value.strip().split(" ", 1)
            h, m, *rest = time_part.split(":")
            return int(h) * 60 + int(m)
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Unrecognized elapsed-time string: {value!r}") from exc
    if isinstance(value, datetime.timedelta):
        return int(round(value.total_seconds() / 60))
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return value.hour * 60 + value.minute
    raise TypeError(f"Unsupported elapsed-time value type: {type(value)!r}")


def wrap_corrected_journey_minutes(elapsed1_min: int, gap_min: float, elapsed2_min: int) -> int:
    """True gate-to-gate duration, immune to the displayed field's 24h wrap.

    gap_min = (dep_time - arr_time) in real calendar minutes -- already
    wrap-safe since dep_time/arr_time are full pd.Timestamps with dates,
    not time-of-day cells (see module docstring / ASSUMPTIONS.md
    VARSAYIM-14). Rounds to nearest minute (parity with loaders._minutes
    rounding).
    """
    return int(round(elapsed1_min + gap_min + elapsed2_min))

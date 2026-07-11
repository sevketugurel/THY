"""Input-file identity stamping for full-data run logs.

A filename alone doesn't prove the content wasn't silently swapped (M5e,
2026-07-11: data_raw/'s O&D file was RENAMED in place from the organizer's
v2 package, not copied -- provenance stamping lets every run log prove
which exact bytes it actually read, independent of path/filename history).
"""
import hashlib
from pathlib import Path


def file_provenance(path) -> dict:
    """Returns {"path": absolute path str, "sha256": hex digest, "size_bytes": int}
    for the given input file. Raises FileNotFoundError if it doesn't exist."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"provenance: file does not exist: {p}")
    data = p.read_bytes()
    return {
        "path": str(p.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }

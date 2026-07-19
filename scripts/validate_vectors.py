"""Validate the shape of every vector file under vectors/. Stdlib only.

Catches malformed vectors independently of the reference test run: a vector
file must parse, carry the family header, and every vector must have exactly
the declared input fields with hash-or-unknown values and a valid expected
action.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[1]

LADDER_INPUT_FIELDS = {
    "local_hash",
    "last_sync_hash",
    "server_content_hash",
    "last_sync_server_hash",
}
LADDER_EXPECTED = {"download", "conflict"}


def fail(path: Path, message: str) -> NoReturn:
    print(f"{path.relative_to(REPO_ROOT)}: {message}")
    raise SystemExit(1)


def validate_ladder_file(path: Path) -> int:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(path, f"not valid JSON: {exc}")
    for key in ("family", "spec", "description", "vectors"):
        if key not in data:
            fail(path, f"missing top-level key {key!r}")
    if data["family"] != "upload-409-ladder":
        fail(path, f"unknown family {data['family']!r}")
    names = set()
    for idx, vector in enumerate(data["vectors"]):
        where = f"vector #{idx}"
        name = vector.get("name")
        if not isinstance(name, str) or not name:
            fail(path, f"{where}: missing or empty name")
        if name in names:
            fail(path, f"{where}: duplicate name {name!r}")
        names.add(name)
        inp = vector.get("input")
        if not isinstance(inp, dict) or set(inp) != LADDER_INPUT_FIELDS:
            fail(path, f"{name}: input must have exactly the fields {sorted(LADDER_INPUT_FIELDS)}")
        for field, value in inp.items():
            if value is not None and not isinstance(value, str):
                fail(path, f"{name}: {field} must be a string or null")
        if vector.get("expected") not in LADDER_EXPECTED:
            fail(path, f"{name}: expected must be one of {sorted(LADDER_EXPECTED)}")
    return len(data["vectors"])


def main() -> None:
    files = sorted((REPO_ROOT / "vectors" / "ladder").glob("*.json"))
    if not files:
        print("no vector files found under vectors/ladder/")
        raise SystemExit(1)
    total = sum(validate_ladder_file(path) for path in files)
    print(f"OK: {total} vectors across {len(files)} files")


if __name__ == "__main__":
    main()

"""Validate the shape of every vector file under vectors/. Stdlib only.

Catches malformed vectors independently of the reference test run: a vector
file must parse, carry the family header matching its directory, and every
vector must have exactly the family's declared input fields and a well-formed
expected value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn

REPO_ROOT = Path(__file__).resolve().parents[1]

LADDER_INPUT_FIELDS = {
    "local_hash",
    "last_sync_hash",
    "server_content_hash",
    "last_sync_server_hash",
}
LADDER_EXPECTED = {"download", "conflict"}

TABLE_INPUT_FIELDS = {
    "local_file",
    "server_saves_in_slot",
    "files_state",
    "device_id",
    "local_hash",
}
TABLE_FILES_STATE_FIELDS = {"last_sync_hash", "last_sync_server_hash", "last_sync_local_size"}
# The decision-table actions. Kept in step with TABLE_EXPECTED_SHAPES below by
# construction — see the assertion next to it.
TABLE_ACTIONS = {"skip", "upload", "download", "conflict"}


class VectorError(Exception):
    pass


def fail(message: str) -> NoReturn:
    raise VectorError(message)


def _hash_or_unknown(name: str, field: str, value: Any) -> None:
    if value is not None and not isinstance(value, str):
        fail(f"{name}: {field} must be a string or null")


def validate_ladder_vector(vector: dict[str, Any]) -> None:
    name = vector["name"]
    inp = vector.get("input")
    if not isinstance(inp, dict) or set(inp) != LADDER_INPUT_FIELDS:
        fail(f"{name}: input must have exactly the fields {sorted(LADDER_INPUT_FIELDS)}")
    for field, value in inp.items():
        _hash_or_unknown(name, field, value)
    if vector.get("expected") not in LADDER_EXPECTED:
        fail(f"{name}: expected must be one of {sorted(LADDER_EXPECTED)}")


def _validate_local_file(name: str, local_file: Any) -> None:
    if local_file is None:
        return
    if not isinstance(local_file, dict):
        fail(f"{name}: local_file must be an object or null")
    if not isinstance(local_file.get("filename"), str):
        fail(f"{name}: local_file.filename must be a string")
    size = local_file.get("size")
    if size is not None and not isinstance(size, int):
        fail(f"{name}: local_file.size must be an integer or null")
    mtime = local_file.get("mtime")
    if mtime is not None and not isinstance(mtime, int | float):
        fail(f"{name}: local_file.mtime must be a number or null")


def _validate_server_saves(name: str, saves: Any) -> None:
    if not isinstance(saves, list):
        fail(f"{name}: server_saves_in_slot must be a list")
    for save in saves:
        if not isinstance(save, dict) or not isinstance(save.get("id"), int):
            fail(f"{name}: every server save must be an object with an integer id")
        if not isinstance(save.get("updated_at"), str):
            fail(f"{name}: server save {save.get('id')}: updated_at must be a string")
        _hash_or_unknown(name, f"server save {save.get('id')} content_hash", save.get("content_hash"))
        syncs = save.get("device_syncs")
        if not isinstance(syncs, list):
            fail(f"{name}: server save {save.get('id')}: device_syncs must be a list")
        for entry in syncs:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("device_id"), str)
                or not isinstance(entry.get("is_current"), bool)
            ):
                fail(f"{name}: device_syncs entries must be {{device_id: string, is_current: bool}}")


def _check_skip_fields(name: str, expected: dict[str, Any]) -> None:
    if not isinstance(expected["reason"], str) or not isinstance(expected["adopt_baseline"], bool):
        fail(f"{name}: skip reason must be a string, adopt_baseline a bool")


def _check_upload_fields(name: str, expected: dict[str, Any]) -> None:
    target_save_id = expected["target_save_id"]
    if target_save_id is not None and not isinstance(target_save_id, int):
        fail(f"{name}: upload target_save_id must be an integer or null")


def _check_server_save_fields(name: str, expected: dict[str, Any]) -> None:
    if not isinstance(expected["server_save_id"], int):
        fail(f"{name}: {expected['action']} server_save_id must be an integer")


# action → (the exact key set it must carry, the check for those keys' values).
# The tagged shapes of the decision-table dialect, one row each, so a new action
# is a row rather than another branch.
TABLE_EXPECTED_SHAPES = {
    "skip": ({"action", "reason", "adopt_baseline"}, _check_skip_fields),
    "upload": ({"action", "target_save_id"}, _check_upload_fields),
    "download": ({"action", "server_save_id"}, _check_server_save_fields),
    "conflict": ({"action", "server_save_id"}, _check_server_save_fields),
}

# An action accepted above but missing here would raise KeyError on a real
# vector instead of failing with a shape message; keep the two in step.
assert set(TABLE_EXPECTED_SHAPES) == TABLE_ACTIONS


def _validate_table_expected(name: str, expected: Any) -> None:
    if not isinstance(expected, dict) or expected.get("action") not in TABLE_ACTIONS:
        fail(f"{name}: expected.action must be one of {sorted(TABLE_ACTIONS)}")
    action = expected["action"]
    fields, check_values = TABLE_EXPECTED_SHAPES[action]
    if set(expected) != fields:
        fail(f"{name}: {action} expects exactly {'/'.join(sorted(fields))}")
    check_values(name, expected)


def validate_table_vector(vector: dict[str, Any]) -> None:
    name = vector["name"]
    inp = vector.get("input")
    if not isinstance(inp, dict) or set(inp) != TABLE_INPUT_FIELDS:
        fail(f"{name}: input must have exactly the fields {sorted(TABLE_INPUT_FIELDS)}")
    _validate_local_file(name, inp["local_file"])
    _validate_server_saves(name, inp["server_saves_in_slot"])
    files_state = inp["files_state"]
    if not isinstance(files_state, dict) or not set(files_state) <= TABLE_FILES_STATE_FIELDS:
        fail(f"{name}: files_state keys must be a subset of {sorted(TABLE_FILES_STATE_FIELDS)}")
    _hash_or_unknown(name, "files_state.last_sync_hash", files_state.get("last_sync_hash"))
    _hash_or_unknown(name, "files_state.last_sync_server_hash", files_state.get("last_sync_server_hash"))
    size = files_state.get("last_sync_local_size")
    if size is not None and not isinstance(size, int):
        fail(f"{name}: files_state.last_sync_local_size must be an integer or null")
    if not isinstance(inp["device_id"], str):
        fail(f"{name}: device_id must be a string")
    _hash_or_unknown(name, "local_hash", inp["local_hash"])
    _validate_table_expected(name, vector.get("expected"))


FAMILIES = {
    "ladder": ("upload-409-ladder", validate_ladder_vector),
    "decision-table": ("decision-table", validate_table_vector),
}


def validate_file(path: Path, family_name: str, validate_vector) -> int:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"not valid JSON: {exc}")
    for key in ("family", "spec", "description", "vectors"):
        if key not in data:
            fail(f"missing top-level key {key!r}")
    if data["family"] != family_name:
        fail(f"family must be {family_name!r}, got {data['family']!r}")
    names = set()
    for idx, vector in enumerate(data["vectors"]):
        name = vector.get("name")
        if not isinstance(name, str) or not name:
            fail(f"vector #{idx}: missing or empty name")
        if name in names:
            fail(f"vector #{idx}: duplicate name {name!r}")
        names.add(name)
        validate_vector(vector)
    return len(data["vectors"])


def main() -> None:
    total = 0
    file_count = 0
    for directory, (family_name, validate_vector) in sorted(FAMILIES.items()):
        files = sorted((REPO_ROOT / "vectors" / directory).glob("*.json"))
        if not files:
            print(f"no vector files found under vectors/{directory}/")
            raise SystemExit(1)
        for path in files:
            try:
                total += validate_file(path, family_name, validate_vector)
            except VectorError as exc:
                print(f"{path.relative_to(REPO_ROOT)}: {exc}")
                raise SystemExit(1) from None
            file_count += 1
    print(f"OK: {total} vectors across {file_count} files")


if __name__ == "__main__":
    main()

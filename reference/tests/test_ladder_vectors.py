"""Run every ladder vector against the reference implementation.

The vectors are the normative artifact; this test is the reference
implementation's conformance run. A port becomes conformant by passing the same
vectors, not by matching this code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "reference"))

from gavel_reference import resolve_upload_conflict  # noqa: E402

_VECTOR_DIR = _REPO_ROOT / "vectors" / "ladder"


def _load_vectors():
    files = sorted(_VECTOR_DIR.glob("*.json"))
    assert files, f"no vector files found in {_VECTOR_DIR}"
    for path in files:
        data = json.loads(path.read_text())
        for vector in data["vectors"]:
            yield pytest.param(vector, id=f"{path.stem}:{vector['name']}")


@pytest.mark.parametrize("vector", list(_load_vectors()))
def test_ladder_vector(vector):
    i = vector["input"]
    got = resolve_upload_conflict(
        i["local_hash"],
        i["last_sync_hash"],
        i["server_content_hash"],
        i["last_sync_server_hash"],
    )
    assert got == vector["expected"], vector.get("rationale", vector["name"])

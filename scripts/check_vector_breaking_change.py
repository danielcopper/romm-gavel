"""Enforce the breaking-change marker when a PR changes the vector contract.

The contract is the mapping *input → expected* per family — names, rationales,
file organization, and prose are presentation. A PR breaks the contract when,
for any family, an input that existed on the base ref now maps to a different
``expected`` (a guarantee changed) or no longer exists at all (a guarantee
disappeared). Additions only grow the contract.

A breaking PR must say so where release-please reads it: the squash commit is
the PR title (+ body), so the title needs the ``!`` marker (``feat!:`` /
``feat(scope)!:``) or the body a ``BREAKING CHANGE`` footer — that is what
turns into the major bump. Run locally with no env vars to just see the
verdict; CI passes ``PR_TITLE`` / ``PR_BODY`` and fails the job when a
breaking change lacks the marker. Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTOR_GLOB = "vectors/*/*.json"
TITLE_BANG = re.compile(r"^[a-z]+(\([^)]*\))?!:")


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _contract_at(ref: str | None) -> dict[str, dict[str, str]]:
    """family → {canonical input JSON → canonical expected JSON} at *ref* (None = worktree)."""
    contract: dict[str, dict[str, str]] = {}
    if ref is None:
        paths = sorted(REPO_ROOT.glob(VECTOR_GLOB))
        blobs = [p.read_text() for p in paths]
    else:
        listed = _git("ls-tree", "-r", "--name-only", ref).splitlines()
        blobs = [
            _git("show", f"{ref}:{path}")
            for path in listed
            if re.fullmatch(r"vectors/[^/]+/[^/]+\.json", path)
        ]
    for text in blobs:
        data = json.loads(text)
        family = contract.setdefault(data["family"], {})
        for vector in data["vectors"]:
            key = json.dumps(vector["input"], sort_keys=True)
            family[key] = json.dumps(vector["expected"], sort_keys=True)
    return contract


def find_breaking_changes(base_ref: str) -> list[str]:
    base = _contract_at(base_ref)
    head = _contract_at(None)
    findings: list[str] = []
    for family, base_map in sorted(base.items()):
        head_map = head.get(family, {})
        for key, base_expected in base_map.items():
            head_expected = head_map.get(key)
            if head_expected is None:
                findings.append(f"{family}: a guaranteed input was removed (was -> {base_expected})")
            elif head_expected != base_expected:
                findings.append(f"{family}: expected changed {base_expected} -> {head_expected}")
    return findings


def main() -> None:
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    merge_base = _git("merge-base", base_ref, "HEAD").strip()
    findings = find_breaking_changes(merge_base)

    if not findings:
        print("OK: no contract-breaking vector changes")
        return

    print(f"CONTRACT-BREAKING vector changes vs {base_ref}:")
    for finding in findings:
        print(f"  - {finding}")

    title = os.environ.get("PR_TITLE")
    body = os.environ.get("PR_BODY") or ""
    if title is None:
        # Local run: report only.
        print("(local run — in CI the PR title must carry '!' or the body a BREAKING CHANGE footer)")
        return

    if TITLE_BANG.match(title) or "BREAKING CHANGE" in body:
        print("OK: breaking-change marker present")
        return

    print(
        "ERROR: this PR changes the vector contract but neither the PR title "
        "carries the '!' marker (e.g. 'feat!: ...') nor the body a "
        "'BREAKING CHANGE' footer. release-please reads the squash commit — "
        "without the marker this would ship as a non-major release."
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()

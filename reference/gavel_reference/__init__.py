"""Reference implementation of the gavel normative core.

Executable form of SPEC.md's normative sections. Conformance is decided by the
vectors in ``vectors/``, not by this code — the reference exists so the vectors
have a first consumer and so ports have something concrete to read.
"""

from gavel_reference.ladder import local_matches_server, resolve_upload_conflict

__all__ = ["local_matches_server", "resolve_upload_conflict"]

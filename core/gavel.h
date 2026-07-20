/* gavel.h — the 409 resolution ladder and the identity check.
 *
 * Native C99 port of the gavel normative core (SPEC.md — "The identity check"
 * and "The 409 resolution ladder"). Pure functions: content hashes in, a
 * decision out. No allocation, no globals, no I/O; every function is
 * reentrant and thread-safe.
 *
 * Inputs are content hashes as produced by RomM (a save's ``content_hash``) or
 * recorded by the client at a sync boundary (its own baseline hash plus the
 * server-stamped hash). NULL and the empty string "" both mean "unknown" and
 * never prove anything — a missing or empty hash on either side never reads as
 * a match.
 *
 * Conformance is decided by the vectors in ``vectors/ladder/``, not by this
 * code; the C behavior is identical to ``reference/gavel_reference/ladder.py``.
 */
#ifndef GAVEL_H
#define GAVEL_H

#ifdef __cplusplus
extern "C" {
#endif

/* The two outcomes of the 409 resolution ladder.
 *
 * GAVEL_DOWNLOAD — the two provably-safe cases: the client holds no un-synced
 *   work, or its local bytes are identical to the server head. Adopting the
 *   server copy loses nothing.
 * GAVEL_CONFLICT — local carries changes AND the server independently moved.
 *   The safe default under uncertainty, surfaced for a user decision.
 */
typedef enum {
    GAVEL_DOWNLOAD = 0,
    GAVEL_CONFLICT = 1
} gavel_resolution;

/* Whether the present local file is byte-identical to a server save.
 *
 * A disjunction of two routes, so a divergence between the client's local
 * hashing and the server's own scheme never silently breaks identity:
 *
 *   - Provenance (primary): the local file is unchanged since the recorded
 *     baseline (``local_hash == last_sync_hash``) AND that baseline was synced
 *     against this exact server content (``last_sync_server_hash ==
 *     server_content_hash``). Both compared server-side values are hashes the
 *     server itself produced, so this route holds even if the client's hashing
 *     drifts from the server's.
 *   - Parity (fallback): the local content hash equals the server content hash
 *     directly. The only route available to a file with no sync history on this
 *     device (fresh reinstall, copied storage, second device).
 *
 * Every compared value must be truthy (non-NULL and non-empty); an unknown hash
 * on either side never reads as a match.
 *
 * Returns 1 when the local file matches a server save, 0 otherwise.
 */
int gavel_local_matches_server(const char *local_hash,
                               const char *server_content_hash,
                               const char *last_sync_hash,
                               const char *last_sync_server_hash);

/* Decide the fallback after the server rejected an upload with 409.
 *
 * The 409 on an ``overwrite=false`` POST proves the slot's head moved past what
 * this device last synced. The client re-decides from hashes alone, in order:
 *
 *   - L1 — local unchanged since the recorded baseline
 *     (``local_hash == last_sync_hash``, both truthy): no un-synced work to
 *     protect → GAVEL_DOWNLOAD.
 *   - L2 — local byte-identical to the server head
 *     (gavel_local_matches_server): adopting identical bytes loses nothing →
 *     GAVEL_DOWNLOAD.
 *   - L3 — otherwise local carries changes and the server independently moved →
 *     GAVEL_CONFLICT.
 *
 * Missing or empty information never yields GAVEL_DOWNLOAD — the safe default
 * under uncertainty is GAVEL_CONFLICT.
 */
gavel_resolution gavel_resolve_upload_conflict(const char *local_hash,
                                               const char *last_sync_hash,
                                               const char *server_content_hash,
                                               const char *last_sync_server_hash);

#ifdef __cplusplus
}
#endif

#endif /* GAVEL_H */

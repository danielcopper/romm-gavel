/* gavel.h — the 409 resolution ladder, the identity check, and the full sync
 * decision.
 *
 * Native C99 port of the gavel core (SPEC.md — "The identity check", "The 409
 * resolution ladder" and the decision table). Pure functions: state in, a
 * decision out. No allocation, no globals, no I/O; every function is reentrant
 * and thread-safe. The caller owns every buffer passed in; the core never
 * stores a pointer past the call that received it.
 *
 * Hash inputs are content hashes as produced by RomM (a save's
 * ``content_hash``) or recorded by the client at a sync boundary (its own
 * baseline hash plus the server-stamped hash). NULL and the empty string ""
 * both mean "unknown" and never prove anything — a missing or empty hash on
 * either side never reads as a match.
 *
 * Conformance is decided by the vectors in ``vectors/``, not by this code; the
 * C behavior is identical to ``reference/gavel_reference/``.
 */
#ifndef GAVEL_H
#define GAVEL_H

#include <stddef.h> /* size_t */
#include <stdint.h> /* int64_t */

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
typedef enum { GAVEL_DOWNLOAD = 0, GAVEL_CONFLICT = 1 } gavel_resolution;

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
int gavel_local_matches_server(const char *local_hash, const char *server_content_hash, const char *last_sync_hash,
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
gavel_resolution gavel_resolve_upload_conflict(const char *local_hash, const char *last_sync_hash,
                                               const char *server_content_hash, const char *last_sync_server_hash);

/* ---------------------------------------------------------------------------
 * The full sync decision (SPEC.md — "Decision table")
 *
 * One decision per (rom, filename, slot). Clients that consume negotiate's
 * verdicts directly don't need this; it exists for clients that, like the
 * reference client, compute detection themselves.
 *
 * Everything is passed as caller-owned structs — no JSON, no allocation. Two
 * conventions run through all of them:
 *
 *   - Arrays arrive as a pointer plus an element count. A count of 0 makes the
 *     pointer irrelevant (it may be NULL).
 *   - An optional number carries an explicit ``has_*`` companion flag rather
 *     than a sentinel value. A sentinel would collapse "absent" and a real
 *     value, and the decision needs them apart: a size of 0 is meaningful
 *     (it is exactly what the corrupt-local guard looks for), so it cannot
 *     double as "no size recorded".
 * ------------------------------------------------------------------------- */

/* One device's sync record on a server save (RomM's ``device_syncs`` entry).
 *
 * ``device_id`` is an opaque identifier compared for plain equality — unlike a
 * hash, an empty id is a real (if odd) value, and two absent ids compare equal.
 * ``is_current`` is a boolean: nonzero means the server still tracks this
 * device's last version on that save. */
typedef struct {
    const char *device_id;
    int is_current;
} gavel_device_sync;

/* One RomM save in the slot.
 *
 * ``updated_at_epoch`` is the save's ``updated_at`` as epoch seconds, with
 * ``has_updated_at`` clear when the client could not parse it. Parsing is
 * deliberately the caller's job: the core stays a decision machine, and every
 * host language already has a correct ISO-8601 parser. What is contract — that
 * an unparseable timestamp loses head selection, and cannot prove local-newer
 * on the fall-through path — lives here, as the ``has_updated_at == 0``
 * behavior. Bindings must map "unparseable" to a clear flag rather than to
 * some fallback instant. */
typedef struct {
    int64_t id;
    double updated_at_epoch;
    int has_updated_at;
    const char *content_hash;
    const gavel_device_sync *device_syncs;
    size_t device_sync_count;
} gavel_server_save;

/* The local file, when one exists.
 *
 * ``size`` backs the corrupt-local guard (invariant I3) and ``mtime`` (epoch
 * seconds) the timestamp fall-through; each is optional. The filename is not a
 * field: it addresses which slot is being decided, and the decision itself
 * never reads it. */
typedef struct {
    int64_t size;
    int has_size;
    double mtime;
    int has_mtime;
} gavel_local_file;

/* The client's bookkeeping record for this file (SPEC.md — "Bookkeeping").
 *
 * The hashes follow the usual rule (NULL or "" means unknown); the recorded
 * local size is optional via ``has_last_sync_local_size``. */
typedef struct {
    const char *last_sync_hash;
    const char *last_sync_server_hash;
    int64_t last_sync_local_size;
    int has_last_sync_local_size;
} gavel_bookkeeping;

/* What the client should do with this (rom, filename, slot). */
typedef enum {
    GAVEL_ACTION_SKIP = 0,
    GAVEL_ACTION_UPLOAD = 1,
    GAVEL_ACTION_DOWNLOAD = 2,
    GAVEL_ACTION_CONFLICT = 3
} gavel_action;

/* Why a GAVEL_ACTION_SKIP decision does nothing. */
typedef enum { GAVEL_SKIP_SYNCED = 0, GAVEL_SKIP_NOTHING_TO_SYNC = 1 } gavel_skip_reason;

/* The decision — a tagged union in struct form: ``action`` says which of the
 * remaining fields carry meaning.
 *
 *   GAVEL_ACTION_SKIP      → ``reason`` and ``adopt_baseline`` (nonzero means
 *                            the client should record the current local file as
 *                            its baseline for this server version)
 *   GAVEL_ACTION_UPLOAD    → ``target_save_id`` when ``has_target_save_id`` is
 *                            nonzero: the save this upload supersedes. Clear
 *                            means there is no such save (a first upload into
 *                            the slot, or the timestamp fall-through).
 *   GAVEL_ACTION_DOWNLOAD  → ``server_save_id``, always the chosen head
 *   GAVEL_ACTION_CONFLICT  → ``server_save_id``, always the chosen head
 *
 * Every field is written on every return: the ones the action names carry the
 * decision, the rest are set to 0. Struct padding is not written and its
 * contents are unspecified — compare two results field by field, never with
 * memcmp. */
typedef struct {
    gavel_action action;
    gavel_skip_reason reason;
    int adopt_baseline;
    int64_t target_save_id;
    int has_target_save_id;
    int64_t server_save_id;
} gavel_sync_action;

/* Compute the sync decision for a single (rom, filename, slot).
 *
 * With no server saves in the slot the decision is trivial: upload a local file
 * if there is one, otherwise there is nothing to sync. Otherwise the newest
 * save by ``updated_at_epoch`` becomes the head (ties and unparseable
 * timestamps resolve to the earliest such element, matching the reference), and
 * this device's ``device_syncs`` entry on that head selects one of the three
 * branches of SPEC.md's decision table.
 *
 *   local_file       — NULL when the file does not exist locally
 *   saves/save_count — the slot's server saves; count 0 means none
 *   bookkeeping      — NULL when this device holds no record for the file
 *   device_id        — this device's RomM registration id
 *   local_hash       — content hash of the local file, NULL or "" if unknown
 *   out              — receives the decision; must not be NULL
 *
 * Every pointer argument is read-only and borrowed for the duration of the
 * call. Passing NULL for ``out`` is the caller's bug, not a handled case. */
void gavel_compute_sync_action(const gavel_local_file *local_file, const gavel_server_save *saves, size_t save_count,
                               const gavel_bookkeeping *bookkeeping, const char *device_id, const char *local_hash,
                               gavel_sync_action *out);

#ifdef __cplusplus
}
#endif

#endif /* GAVEL_H */

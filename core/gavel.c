/* gavel.c — implementation of the 409 resolution ladder, the identity check,
 * and the full sync decision.
 *
 * See gavel.h for the contract. Behaviorally identical to
 * reference/gavel_reference/; the JSON vectors decide conformance.
 */
#include "gavel.h"

/* Freestanding on purpose. The only libc symbol this file ever needed was
 * strcmp; inlining the comparison makes the compiled library import NOTHING,
 * so it loads on any x86_64 Linux regardless of libc flavor or version. The
 * release pipeline enforces this with a zero-undefined-symbols guard.
 * <stddef.h> (for NULL) is a compiler-provided freestanding header — it adds
 * no runtime dependency, and neither does <stdint.h>; both come in via
 * gavel.h. */
#include <stddef.h>

/* "Truthy" — non-NULL and non-empty, mirroring the reference's rule that NULL
 * and "" both mean "unknown". */
static int gavel_truthy(const char *s) { return s != NULL && s[0] != '\0'; }

/* Byte-equality of two NUL-terminated strings (strcmp(a, b) == 0, inlined to
 * keep the library dependency-free). Callers guarantee non-NULL. */
static int gavel_bytes_equal(const char *a, const char *b) {
    while (*a != '\0' && *a == *b) {
        a++;
        b++;
    }
    return *a == *b;
}

/* Whether two hashes are both truthy and byte-equal.
 *
 * The C form of the reference's ``bool(a) and a == b``: an unknown value on
 * either side (NULL or "") is never equal to anything. */
static int gavel_truthy_equal(const char *a, const char *b) {
    return gavel_truthy(a) && gavel_truthy(b) && gavel_bytes_equal(a, b);
}

int gavel_local_matches_server(const char *local_hash, const char *server_content_hash, const char *last_sync_hash,
                               const char *last_sync_server_hash) {
    /* Provenance: local unchanged since baseline, and that baseline was synced
     * against this exact server content. */
    if (gavel_truthy_equal(local_hash, last_sync_hash) &&
        gavel_truthy_equal(last_sync_server_hash, server_content_hash)) {
        return 1;
    }
    /* Parity: the local content hash equals the server content hash directly. */
    return gavel_truthy_equal(local_hash, server_content_hash);
}

gavel_resolution gavel_resolve_upload_conflict(const char *local_hash, const char *last_sync_hash,
                                               const char *server_content_hash, const char *last_sync_server_hash) {
    /* L1 — unchanged since baseline: no un-synced work to protect. */
    if (gavel_truthy_equal(local_hash, last_sync_hash)) {
        return GAVEL_DOWNLOAD;
    }
    /* L2 — byte-identical to the server head: adopting identical bytes is safe. */
    if (gavel_local_matches_server(local_hash, server_content_hash, last_sync_hash, last_sync_server_hash)) {
        return GAVEL_DOWNLOAD;
    }
    /* L3 — local changed and the server independently moved. */
    return GAVEL_CONFLICT;
}

/* ---------------------------------------------------------------------------
 * The full sync decision
 * ------------------------------------------------------------------------- */

/* Plain byte equality, NULL-safe: an empty string is a real value that equals
 * another empty string, and two absent values compare equal (mirroring the
 * reference, where a missing key on both sides is ``None == None``).
 *
 * This is not gavel_truthy_equal. Whether an unknown value proves anything is a
 * property of the *comparison*, not of the operands: device ids are compared
 * for plain identity, and so is a local hash against its baseline — there the
 * "unknown proves nothing" rule sits on the local hash alone, applied by the
 * caller. Only the identity check itself is built from gavel_truthy_equal. */
static int gavel_ids_equal(const char *a, const char *b) {
    if (a == NULL || b == NULL) {
        return a == b;
    }
    return gavel_bytes_equal(a, b);
}

/* Whether the local file has demonstrably changed since the baseline.
 *
 * Requires a known local hash: an unknown one cannot prove divergence, so it
 * reads as "not diverged" and the caller's unchanged path applies. */
static int gavel_diverged_from_baseline(const char *local_hash, const char *last_sync_hash) {
    return gavel_truthy(local_hash) && !gavel_ids_equal(local_hash, last_sync_hash);
}

/* The corrupt-local guard (invariant I3): is this file implausibly smaller than
 * the size recorded at the last sync boundary?
 *
 * A 0-byte file is never a plausible edit. Below half the recorded size means a
 * truncated write. The threshold is the reference's ``size < baseline * 0.5``
 * rearranged into ``size < baseline - size`` — exact integer arithmetic that
 * cannot overflow (both operands are positive by the time it runs) and needs no
 * floating point. */
static int gavel_implausibly_shrunken(const gavel_local_file *local_file, const gavel_bookkeeping *bookkeeping) {
    if (!local_file->has_size) {
        return 0;
    }
    if (local_file->size == 0) {
        return 1;
    }
    if (bookkeeping == NULL || !bookkeeping->has_last_sync_local_size || bookkeeping->last_sync_local_size <= 0) {
        return 0;
    }
    if (local_file->size < 0) {
        /* Nonsense from the caller, but it is below every positive threshold —
         * decided here so the subtraction below only ever sees positives. */
        return 1;
    }
    return local_file->size < bookkeeping->last_sync_local_size - local_file->size;
}

/* The timestamp fall-through: is the local file at least as new as the head?
 *
 * Either side being unknown means no — the local file cannot be proven newer,
 * so the server copy wins. A tie counts as local-newer (at-or-after). */
static int gavel_local_mtime_ge_head(const gavel_local_file *local_file, const gavel_server_save *head) {
    if (!local_file->has_mtime || !head->has_updated_at) {
        return 0;
    }
    return local_file->mtime >= head->updated_at_epoch;
}

/* Sort key for head selection: an unknown timestamp sorts as epoch 0, which is
 * what makes it lose to any save with a real (positive) one. */
static double gavel_head_sort_key(const gavel_server_save *save) {
    return save->has_updated_at ? save->updated_at_epoch : 0.0;
}

/* The newest save in the slot by ``updated_at``.
 *
 * Strictly-greater comparison, so a tie keeps the earlier element — the same
 * first-maximum-wins rule as the reference's ``max(..., key=...)``. Callers
 * guarantee a non-empty array. */
static const gavel_server_save *gavel_pick_head(const gavel_server_save *saves, size_t save_count) {
    const gavel_server_save *head = &saves[0];
    double best = gavel_head_sort_key(head);

    for (size_t i = 1; i < save_count; i++) {
        double key = gavel_head_sort_key(&saves[i]);
        if (key > best) {
            head = &saves[i];
            best = key;
        }
    }
    return head;
}

/* This device's ``device_syncs`` entry on the head, or NULL if it has none. */
static const gavel_device_sync *gavel_find_device_sync(const gavel_server_save *head, const char *device_id) {
    if (head->device_syncs == NULL) {
        return NULL;
    }
    for (size_t i = 0; i < head->device_sync_count; i++) {
        if (gavel_ids_equal(head->device_syncs[i].device_id, device_id)) {
            return &head->device_syncs[i];
        }
    }
    return NULL;
}

/* Result constructors. Each starts from an all-zero struct so the fields the
 * action does not name are always defined, never leftovers. */

static void gavel_clear(gavel_sync_action *out) {
    out->action = GAVEL_ACTION_SKIP;
    out->reason = GAVEL_SKIP_SYNCED;
    out->adopt_baseline = 0;
    out->target_save_id = 0;
    out->has_target_save_id = 0;
    out->server_save_id = 0;
}

static void gavel_set_skip(gavel_sync_action *out, gavel_skip_reason reason, int adopt_baseline) {
    gavel_clear(out);
    out->action = GAVEL_ACTION_SKIP;
    out->reason = reason;
    out->adopt_baseline = adopt_baseline;
}

/* ``target`` is the save this upload supersedes, or NULL when there is none. */
static void gavel_set_upload(gavel_sync_action *out, const gavel_server_save *target) {
    gavel_clear(out);
    out->action = GAVEL_ACTION_UPLOAD;
    if (target != NULL) {
        out->target_save_id = target->id;
        out->has_target_save_id = 1;
    }
}

static void gavel_set_download(gavel_sync_action *out, const gavel_server_save *head) {
    gavel_clear(out);
    out->action = GAVEL_ACTION_DOWNLOAD;
    out->server_save_id = head->id;
}

static void gavel_set_conflict(gavel_sync_action *out, const gavel_server_save *head) {
    gavel_clear(out);
    out->action = GAVEL_ACTION_CONFLICT;
    out->server_save_id = head->id;
}

/* Branch 1 — is_current=true: the server still tracks this device's last
 * version on the head. */
static void gavel_decide_when_is_current(const gavel_server_save *head, const gavel_local_file *local_file,
                                         const char *local_hash, const char *last_sync_hash,
                                         const gavel_bookkeeping *bookkeeping, gavel_sync_action *out) {
    if (local_file == NULL) {
        gavel_set_download(out, head); /* recover the tracked content */
        return;
    }
    if (!gavel_truthy(last_sync_hash)) {
        gavel_set_skip(out, GAVEL_SKIP_SYNCED, 1); /* adopt the current file as baseline */
        return;
    }
    if (gavel_diverged_from_baseline(local_hash, last_sync_hash)) {
        if (gavel_implausibly_shrunken(local_file, bookkeeping)) {
            gavel_set_conflict(out, head);
            return;
        }
        gavel_set_upload(out, head);
        return;
    }
    gavel_set_skip(out, GAVEL_SKIP_SYNCED, 0);
}

/* Branch 2 — is_current=false: the server head moved past this device. */
static void gavel_decide_when_not_current(const gavel_server_save *head, const gavel_local_file *local_file,
                                          const char *local_hash, const char *last_sync_hash,
                                          const char *last_sync_server_hash, gavel_sync_action *out) {
    int identical;

    if (local_file == NULL) {
        gavel_set_download(out, head);
        return;
    }
    /* With no baseline, provenance is unavailable and only byte-identity can
     * justify adopting the head; a diverged local needs the same proof. */
    if (!gavel_truthy(last_sync_hash) || gavel_diverged_from_baseline(local_hash, last_sync_hash)) {
        identical = gavel_local_matches_server(local_hash, head->content_hash, last_sync_hash, last_sync_server_hash);
        if (identical) {
            gavel_set_download(out, head);
        } else {
            gavel_set_conflict(out, head);
        }
        return;
    }
    /* Unchanged since the baseline — nothing of this device's own to protect. */
    gavel_set_download(out, head);
}

/* Branch 3 — no entry: this device never touched the chosen head. */
static void gavel_decide_when_no_entry(const gavel_server_save *head, const gavel_local_file *local_file,
                                       const char *local_hash, const char *last_sync_hash,
                                       const char *last_sync_server_hash, gavel_sync_action *out) {
    if (local_file == NULL) {
        gavel_set_download(out, head);
        return;
    }
    if (gavel_local_matches_server(local_hash, head->content_hash, last_sync_hash, last_sync_server_hash)) {
        gavel_set_skip(out, GAVEL_SKIP_SYNCED, 1); /* don't POST a duplicate */
        return;
    }
    /* A diverged local mirrors the is_current=false branch; an unknown
     * provenance (no baseline but a known local hash) is equally unresolvable. */
    if (gavel_truthy(last_sync_hash) && gavel_diverged_from_baseline(local_hash, last_sync_hash)) {
        gavel_set_conflict(out, head);
        return;
    }
    if (!gavel_truthy(last_sync_hash) && gavel_truthy(local_hash)) {
        gavel_set_conflict(out, head);
        return;
    }
    /* Unchanged, or no hash to compare at all: fall through to timestamps. */
    if (gavel_local_mtime_ge_head(local_file, head)) {
        gavel_set_upload(out, NULL);
        return;
    }
    gavel_set_download(out, head);
}

void gavel_compute_sync_action(const gavel_local_file *local_file, const gavel_server_save *saves, size_t save_count,
                               const gavel_bookkeeping *bookkeeping, const char *device_id, const char *local_hash,
                               gavel_sync_action *out) {
    const gavel_server_save *head;
    const gavel_device_sync *our_entry;
    const char *last_sync_hash = bookkeeping != NULL ? bookkeeping->last_sync_hash : NULL;
    const char *last_sync_server_hash = bookkeeping != NULL ? bookkeeping->last_sync_server_hash : NULL;

    /* An empty slot: the local file, if any, is the only content there is. */
    if (saves == NULL || save_count == 0) {
        if (local_file != NULL) {
            gavel_set_upload(out, NULL);
        } else {
            gavel_set_skip(out, GAVEL_SKIP_NOTHING_TO_SYNC, 0);
        }
        return;
    }

    head = gavel_pick_head(saves, save_count);
    our_entry = gavel_find_device_sync(head, device_id);

    if (our_entry != NULL && our_entry->is_current) {
        gavel_decide_when_is_current(head, local_file, local_hash, last_sync_hash, bookkeeping, out);
        return;
    }
    if (our_entry != NULL) {
        gavel_decide_when_not_current(head, local_file, local_hash, last_sync_hash, last_sync_server_hash, out);
        return;
    }
    gavel_decide_when_no_entry(head, local_file, local_hash, last_sync_hash, last_sync_server_hash, out);
}

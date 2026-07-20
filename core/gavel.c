/* gavel.c — implementation of the 409 resolution ladder and the identity check.
 *
 * See gavel.h for the contract. Behaviorally identical to
 * reference/gavel_reference/ladder.py; the JSON vectors decide conformance.
 */
#include "gavel.h"

/* Freestanding on purpose. The only libc symbol this file ever needed was
 * strcmp; inlining the comparison makes the compiled library import NOTHING,
 * so it loads on any x86_64 Linux regardless of libc flavor or version. The
 * release pipeline enforces this with a zero-undefined-symbols guard.
 * <stddef.h> (for NULL) is a compiler-provided freestanding header — it adds
 * no runtime dependency. */
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

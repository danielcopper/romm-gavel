/* exhaustive_driver.c — full-input-space execution of the gavel core under
 * sanitizers, plus a second, independently coded oracle.
 *
 * Enumerates all 6^4 = 1296 combinations of {NULL, "", and four distinct
 * 32-char hashes} across the four parameters, calls both public functions on
 * every combination, and asserts each result is in range, agrees with an
 * inline re-derivation of the ladder and identity check, and honors three
 * hand-derived invariants.
 *
 * Behavior-correctness authority stays with the JSON vectors; this driver's job
 * is coverage of the whole input space under ASan/UBSan plus a second,
 * independently coded oracle. Exit 0 on success; nonzero with a message on the
 * first failure.
 */
#include <stdio.h>
#include <string.h>

#include "../gavel.h"

/* Independent oracle — coded from the spec, not shared with gavel.c. */

static int is_truthy(const char *s) {
    return s != NULL && s[0] != '\0';
}

static int truthy_equal(const char *a, const char *b) {
    return is_truthy(a) && is_truthy(b) && strcmp(a, b) == 0;
}

/* Independent re-derivation of the identity check. */
static int oracle_matches(const char *local, const char *server,
                          const char *last_sync, const char *last_sync_server) {
    int provenance = truthy_equal(local, last_sync) &&
                     truthy_equal(last_sync_server, server);
    int parity = truthy_equal(local, server);
    return provenance || parity;
}

/* Independent re-derivation of the ladder: DOWNLOAD iff L1 or parity or
 * provenance, else CONFLICT. */
static gavel_resolution oracle_resolve(const char *local, const char *last_sync,
                                       const char *server,
                                       const char *last_sync_server) {
    int l1 = truthy_equal(local, last_sync);
    int identity = oracle_matches(local, server, last_sync, last_sync_server);
    return (l1 || identity) ? GAVEL_DOWNLOAD : GAVEL_CONFLICT;
}

int main(void) {
    const char *alphabet[6];
    alphabet[0] = NULL;
    alphabet[1] = "";
    alphabet[2] = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    alphabet[3] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    alphabet[4] = "cccccccccccccccccccccccccccccccc";
    alphabet[5] = "dddddddddddddddddddddddddddddddd";

    for (int a = 0; a < 6; a++) {
        for (int b = 0; b < 6; b++) {
            for (int c = 0; c < 6; c++) {
                for (int d = 0; d < 6; d++) {
                    const char *local = alphabet[a];
                    const char *last_sync = alphabet[b];
                    const char *server = alphabet[c];
                    const char *last_sync_server = alphabet[d];

                    int m = gavel_local_matches_server(local, server, last_sync,
                                                       last_sync_server);
                    gavel_resolution r = gavel_resolve_upload_conflict(
                        local, last_sync, server, last_sync_server);

                    /* Results in range. */
                    if (m != 0 && m != 1) {
                        fprintf(stderr,
                                "matcher out of range: %d (a=%d b=%d c=%d d=%d)\n",
                                m, a, b, c, d);
                        return 1;
                    }
                    if (r != GAVEL_DOWNLOAD && r != GAVEL_CONFLICT) {
                        fprintf(stderr,
                                "ladder out of range: %d (a=%d b=%d c=%d d=%d)\n",
                                (int)r, a, b, c, d);
                        return 1;
                    }

                    /* Matcher agrees with the oracle identity check. */
                    int want_m = oracle_matches(local, server, last_sync,
                                                last_sync_server);
                    if (m != want_m) {
                        fprintf(stderr,
                                "matcher disagrees with oracle: got %d want %d "
                                "(a=%d b=%d c=%d d=%d)\n",
                                m, want_m, a, b, c, d);
                        return 1;
                    }

                    /* Invariant (iii): DOWNLOAD iff (L1 or parity or provenance). */
                    gavel_resolution want_r = oracle_resolve(
                        local, last_sync, server, last_sync_server);
                    if (r != want_r) {
                        fprintf(stderr,
                                "ladder disagrees with oracle: got %d want %d "
                                "(a=%d b=%d c=%d d=%d)\n",
                                (int)r, (int)want_r, a, b, c, d);
                        return 1;
                    }

                    /* Invariant (i): both hashes equal and truthy → DOWNLOAD. */
                    if (truthy_equal(local, last_sync) && r != GAVEL_DOWNLOAD) {
                        fprintf(stderr,
                                "inv(i) violated: local==last_sync truthy but not "
                                "DOWNLOAD (a=%d b=%d c=%d d=%d)\n",
                                a, b, c, d);
                        return 1;
                    }

                    /* Invariant (ii): local_hash NULL or "" → CONFLICT. */
                    if (!is_truthy(local) && r != GAVEL_CONFLICT) {
                        fprintf(stderr,
                                "inv(ii) violated: local unknown but not CONFLICT "
                                "(a=%d b=%d c=%d d=%d)\n",
                                a, b, c, d);
                        return 1;
                    }
                }
            }
        }
    }

    printf("ok: 1296 combinations; both functions in range, oracle + invariants hold\n");
    return 0;
}

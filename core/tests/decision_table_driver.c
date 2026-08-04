/* decision_table_driver.c — sweep gavel_compute_sync_action under sanitizers,
 * against a second, independently coded oracle.
 *
 * The ladder's inputs are four hashes and can be walked exhaustively
 * (exhaustive_driver.c). The decision table's are nested objects, so this driver
 * crosses the axes that actually branch instead: local file present / absent /
 * incomplete / shrunken, the head's device_syncs entry, whether timestamps are
 * known, and which parts of the bookkeeping record exist. 13968 combinations.
 *
 * Two things are checked on every combination:
 *   - the decision matches an oracle transcribed from SPEC.md's three decision
 *     tables, row by row — deliberately not sharing a line with gavel.c;
 *   - the result struct is well-formed: the action is in range and every field
 *     the action does not name is zero, which is what gavel.h promises.
 *
 * Behavior-correctness authority stays with the JSON vectors; this driver's job
 * is memory-safety coverage under ASan/UBSan plus the independent oracle. Exit 0
 * on success; nonzero with a message on the first failure.
 */
#include <stdio.h>
#include <string.h>

#include "../gavel.h"

#define DEVICE_ID "device-a"
#define OTHER_DEVICE_ID "device-b"

#define HASH_A "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
#define HASH_B "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

/* ---------------------------------------------------------------------------
 * Independent oracle — transcribed from SPEC.md, not from gavel.c.
 * ------------------------------------------------------------------------- */

static int is_truthy(const char *s) { return s != NULL && s[0] != '\0'; }

static int truthy_equal(const char *a, const char *b) { return is_truthy(a) && is_truthy(b) && strcmp(a, b) == 0; }

static int ids_equal(const char *a, const char *b) {
    if (a == NULL || b == NULL) {
        return a == b;
    }
    return strcmp(a, b) == 0;
}

/* SPEC.md — "The identity check": provenance OR parity. */
static int oracle_identity(const char *local, const char *server, const char *last_sync, const char *last_sync_server) {
    return (truthy_equal(local, last_sync) && truthy_equal(last_sync_server, server)) || truthy_equal(local, server);
}

/* SPEC.md — invariant I3, as the reference spells it out: a 0-byte file, or one
 * below half the recorded size. */
static int oracle_shrunken(const gavel_local_file *local_file, const gavel_bookkeeping *bk) {
    double baseline;
    if (!local_file->has_size) {
        return 0;
    }
    if (local_file->size == 0) {
        return 1;
    }
    if (bk == NULL || !bk->has_last_sync_local_size || bk->last_sync_local_size <= 0) {
        return 0;
    }
    baseline = (double)bk->last_sync_local_size * 0.5;
    return (double)local_file->size < baseline;
}

/* The facts SPEC.md's three branch tables read, computed once. */
typedef struct {
    const gavel_server_save *head;
    const gavel_local_file *local_file;
    const gavel_bookkeeping *bk;
    const char *local_hash;
    int present;
    int has_baseline;
    int diverged;
    int identical;
} oracle_facts;

/* Row 2 — newest by updated_at; unknown sorts as 0 and so loses to any positive
 * timestamp. Ties keep the earlier element. */
static const gavel_server_save *oracle_head(const gavel_server_save *saves, size_t save_count) {
    const gavel_server_save *head = &saves[0];
    for (size_t i = 1; i < save_count; i++) {
        double key = saves[i].has_updated_at ? saves[i].updated_at_epoch : 0.0;
        double best = head->has_updated_at ? head->updated_at_epoch : 0.0;
        if (key > best) {
            head = &saves[i];
        }
    }
    return head;
}

static const gavel_device_sync *oracle_entry(const gavel_server_save *head, const char *device_id) {
    for (size_t i = 0; i < head->device_sync_count; i++) {
        if (ids_equal(head->device_syncs[i].device_id, device_id)) {
            return &head->device_syncs[i];
        }
    }
    return NULL;
}

/* Row 3a — is_current=true: the server still tracks this device's version. */
static void oracle_when_is_current(const oracle_facts *f, gavel_sync_action *out) {
    if (!f->present) {
        out->action = GAVEL_ACTION_DOWNLOAD;
    } else if (!f->has_baseline) {
        out->action = GAVEL_ACTION_SKIP;
        out->adopt_baseline = 1;
        out->server_save_id = 0;
    } else if (!f->diverged) {
        out->action = GAVEL_ACTION_SKIP;
        out->server_save_id = 0;
    } else if (oracle_shrunken(f->local_file, f->bk)) {
        out->action = GAVEL_ACTION_CONFLICT;
    } else {
        out->action = GAVEL_ACTION_UPLOAD;
        out->target_save_id = f->head->id;
        out->has_target_save_id = 1;
        out->server_save_id = 0;
    }
}

/* Row 3b — is_current=false: the head moved past this device. */
static void oracle_when_not_current(const oracle_facts *f, gavel_sync_action *out) {
    if (f->present && (!f->has_baseline || f->diverged) && !f->identical) {
        out->action = GAVEL_ACTION_CONFLICT;
    } else {
        out->action = GAVEL_ACTION_DOWNLOAD;
    }
}

/* Row 3c — no entry: this device never touched the chosen head. */
static void oracle_when_no_entry(const oracle_facts *f, gavel_sync_action *out) {
    if (!f->present) {
        out->action = GAVEL_ACTION_DOWNLOAD;
    } else if (f->identical) {
        out->action = GAVEL_ACTION_SKIP;
        out->adopt_baseline = 1;
        out->server_save_id = 0;
    } else if (f->has_baseline && f->diverged) {
        /* Mirrors 3b: local moved and the head is not those bytes. */
        out->action = GAVEL_ACTION_CONFLICT;
    } else if (!f->has_baseline && is_truthy(f->local_hash)) {
        /* A known hash with no baseline at all: provenance is unresolvable. */
        out->action = GAVEL_ACTION_CONFLICT;
    } else if (f->local_file->has_mtime && f->head->has_updated_at &&
               f->local_file->mtime >= f->head->updated_at_epoch) {
        out->action = GAVEL_ACTION_UPLOAD;
        out->server_save_id = 0;
    } else {
        out->action = GAVEL_ACTION_DOWNLOAD;
    }
}

/* The full decision, as SPEC.md's tables read top to bottom. */
static gavel_sync_action oracle_decide(const gavel_local_file *local_file, const gavel_server_save *saves,
                                       size_t save_count, const gavel_bookkeeping *bk, const char *device_id,
                                       const char *local_hash) {
    gavel_sync_action out;
    const gavel_device_sync *entry;
    const char *last_sync = bk != NULL ? bk->last_sync_hash : NULL;
    const char *last_sync_server = bk != NULL ? bk->last_sync_server_hash : NULL;
    oracle_facts f;

    memset(&out, 0, sizeof(out));

    /* Row 1 — nothing on the server side of the slot. */
    if (saves == NULL || save_count == 0) {
        if (local_file != NULL) {
            out.action = GAVEL_ACTION_UPLOAD;
        } else {
            out.action = GAVEL_ACTION_SKIP;
            out.reason = GAVEL_SKIP_NOTHING_TO_SYNC;
        }
        return out;
    }

    f.head = oracle_head(saves, save_count);
    f.local_file = local_file;
    f.bk = bk;
    f.local_hash = local_hash;
    f.present = local_file != NULL;
    f.has_baseline = is_truthy(last_sync);
    f.diverged = is_truthy(local_hash) && !ids_equal(local_hash, last_sync);
    f.identical = oracle_identity(local_hash, f.head->content_hash, last_sync, last_sync_server);
    entry = oracle_entry(f.head, device_id);

    out.server_save_id = f.head->id;
    if (entry != NULL && entry->is_current) {
        oracle_when_is_current(&f, &out);
    } else if (entry != NULL) {
        oracle_when_not_current(&f, &out);
    } else {
        oracle_when_no_entry(&f, &out);
    }
    return out;
}

/* ---------------------------------------------------------------------------
 * The swept input space
 * ------------------------------------------------------------------------- */

#define N_LOCAL_FILES 7
#define N_BOOKKEEPING 6
#define N_HASHES 4
#define N_TIMESTAMPS 4
#define N_SYNC_SETS 5
#define N_SLOTS (1 + N_TIMESTAMPS * N_HASHES * N_SYNC_SETS + N_TIMESTAMPS * N_TIMESTAMPS)

/* Epoch of the "equal" timestamp, so the fall-through sees older / equal /
 * newer local files. */
#define EQUAL_EPOCH 1780401600.0

static const char *const HASHES[N_HASHES] = {NULL, "", HASH_A, HASH_B};

/* {has_updated_at, epoch} — includes 0.0, which ties with "unknown". */
static const int TS_KNOWN[N_TIMESTAMPS] = {0, 1, 1, 1};
static const double TS_EPOCH[N_TIMESTAMPS] = {0.0, 1780315200.0, EQUAL_EPOCH, 0.0};

static gavel_local_file LOCAL_FILES[N_LOCAL_FILES];
static gavel_bookkeeping BOOKKEEPING[N_BOOKKEEPING];
static gavel_device_sync SYNC_ENTRIES[N_SYNC_SETS][2];
static size_t SYNC_COUNTS[N_SYNC_SETS];

static void init_fixtures(void) {
    /* index 0 is unused — the sweep passes NULL for "no local file". */
    LOCAL_FILES[1].has_size = 0;
    LOCAL_FILES[1].has_mtime = 0;
    LOCAL_FILES[2].size = 0;
    LOCAL_FILES[2].has_size = 1;
    LOCAL_FILES[2].mtime = EQUAL_EPOCH;
    LOCAL_FILES[2].has_mtime = 1;
    LOCAL_FILES[3].size = 100; /* below half of an 8192-byte baseline */
    LOCAL_FILES[3].has_size = 1;
    LOCAL_FILES[3].mtime = EQUAL_EPOCH - 3600.0;
    LOCAL_FILES[3].has_mtime = 1;
    LOCAL_FILES[4].size = 8192;
    LOCAL_FILES[4].has_size = 1;
    LOCAL_FILES[4].mtime = EQUAL_EPOCH;
    LOCAL_FILES[4].has_mtime = 1;
    LOCAL_FILES[5].size = 8192;
    LOCAL_FILES[5].has_size = 1;
    LOCAL_FILES[5].mtime = EQUAL_EPOCH + 3600.0;
    LOCAL_FILES[5].has_mtime = 1;
    /* Nonsense from a caller, but it is the input the shrink guard's negative
     * branch exists for — the branch that keeps INT64_MIN out of its
     * subtraction. Without a fixture reaching it, the sanitizers never see it. */
    LOCAL_FILES[6].size = -1;
    LOCAL_FILES[6].has_size = 1;
    LOCAL_FILES[6].mtime = EQUAL_EPOCH;
    LOCAL_FILES[6].has_mtime = 1;

    /* index 0 is unused — the sweep passes NULL for "no record held". */
    BOOKKEEPING[1].last_sync_hash = NULL;
    BOOKKEEPING[1].last_sync_server_hash = NULL;
    BOOKKEEPING[2].last_sync_hash = HASH_A;
    BOOKKEEPING[2].last_sync_server_hash = NULL;
    BOOKKEEPING[3].last_sync_hash = HASH_A;
    BOOKKEEPING[3].last_sync_server_hash = HASH_B;
    BOOKKEEPING[3].last_sync_local_size = 8192;
    BOOKKEEPING[3].has_last_sync_local_size = 1;
    BOOKKEEPING[4].last_sync_hash = "";
    BOOKKEEPING[4].last_sync_server_hash = "";
    BOOKKEEPING[5].last_sync_hash = HASH_B;
    BOOKKEEPING[5].last_sync_server_hash = NULL;
    BOOKKEEPING[5].last_sync_local_size = 0; /* recorded but <= 0: guard stays off */
    BOOKKEEPING[5].has_last_sync_local_size = 1;

    SYNC_COUNTS[0] = 0;
    SYNC_ENTRIES[1][0].device_id = DEVICE_ID;
    SYNC_ENTRIES[1][0].is_current = 1;
    SYNC_COUNTS[1] = 1;
    SYNC_ENTRIES[2][0].device_id = DEVICE_ID;
    SYNC_ENTRIES[2][0].is_current = 0;
    SYNC_COUNTS[2] = 1;
    SYNC_ENTRIES[3][0].device_id = OTHER_DEVICE_ID;
    SYNC_ENTRIES[3][0].is_current = 1;
    SYNC_COUNTS[3] = 1;
    SYNC_ENTRIES[4][0].device_id = OTHER_DEVICE_ID;
    SYNC_ENTRIES[4][0].is_current = 1;
    SYNC_ENTRIES[4][1].device_id = DEVICE_ID;
    SYNC_ENTRIES[4][1].is_current = 0;
    SYNC_COUNTS[4] = 2;
}

/* Fill ``buffer`` with slot number ``index`` and return how many saves it holds.
 * Slot 0 is the empty slot; then every (timestamp, content_hash, sync set) as a
 * single save; then every timestamp pair as a two-save slot, which is what puts
 * head selection itself under test. */
static size_t build_slot(size_t index, gavel_server_save *buffer) {
    size_t single_count = (size_t)(N_TIMESTAMPS * N_HASHES * N_SYNC_SETS);

    memset(buffer, 0, 2 * sizeof(*buffer));
    if (index == 0) {
        return 0;
    }
    index -= 1;

    if (index < single_count) {
        size_t sync_set = index % N_SYNC_SETS;
        size_t hash = (index / N_SYNC_SETS) % N_HASHES;
        size_t ts = (index / (N_SYNC_SETS * N_HASHES)) % N_TIMESTAMPS;

        buffer[0].id = 101;
        buffer[0].has_updated_at = TS_KNOWN[ts];
        buffer[0].updated_at_epoch = TS_EPOCH[ts];
        buffer[0].content_hash = HASHES[hash];
        buffer[0].device_syncs = SYNC_COUNTS[sync_set] > 0 ? SYNC_ENTRIES[sync_set] : NULL;
        buffer[0].device_sync_count = SYNC_COUNTS[sync_set];
        return 1;
    }

    index -= single_count;
    buffer[0].id = 101;
    buffer[0].has_updated_at = TS_KNOWN[index / N_TIMESTAMPS];
    buffer[0].updated_at_epoch = TS_EPOCH[index / N_TIMESTAMPS];
    buffer[0].content_hash = HASH_A;
    buffer[0].device_syncs = SYNC_ENTRIES[1];
    buffer[0].device_sync_count = 1;
    buffer[1].id = 102;
    buffer[1].has_updated_at = TS_KNOWN[index % N_TIMESTAMPS];
    buffer[1].updated_at_epoch = TS_EPOCH[index % N_TIMESTAMPS];
    buffer[1].content_hash = HASH_B;
    buffer[1].device_syncs = SYNC_ENTRIES[2];
    buffer[1].device_sync_count = 1;
    return 2;
}

/* Every field the action does not name must be zero (gavel.h's promise). */
static const char *well_formed(const gavel_sync_action *got) {
    switch (got->action) {
    case GAVEL_ACTION_SKIP:
        if (got->reason != GAVEL_SKIP_SYNCED && got->reason != GAVEL_SKIP_NOTHING_TO_SYNC) {
            return "skip reason out of range";
        }
        if (got->target_save_id != 0 || got->has_target_save_id != 0 || got->server_save_id != 0) {
            return "skip carries save ids";
        }
        return NULL;
    case GAVEL_ACTION_UPLOAD:
        if (got->reason != 0 || got->adopt_baseline != 0 || got->server_save_id != 0) {
            return "upload carries skip/download fields";
        }
        return NULL;
    case GAVEL_ACTION_DOWNLOAD:
    case GAVEL_ACTION_CONFLICT:
        if (got->reason != 0 || got->adopt_baseline != 0 || got->target_save_id != 0 || got->has_target_save_id != 0) {
            return "download/conflict carries skip/upload fields";
        }
        return NULL;
    default:
        return "action out of range";
    }
}

static int actions_equal(const gavel_sync_action *a, const gavel_sync_action *b) {
    return a->action == b->action && a->reason == b->reason && a->adopt_baseline == b->adopt_baseline &&
           a->target_save_id == b->target_save_id && a->has_target_save_id == b->has_target_save_id &&
           a->server_save_id == b->server_save_id;
}

/* Every axis but the slot, as one counter: the digits of `n` are the fixture
 * indices, so the sweep stays a full product without four levels of nesting. */
#define INNER_COMBINATIONS (N_LOCAL_FILES * N_BOOKKEEPING * N_HASHES)

/* One combination: the result is well-formed and matches the oracle. Returns 0
 * and explains on the first failure. */
static int check_combination(const gavel_server_save *saves, size_t save_count, size_t slot_index, size_t local_index,
                             size_t bk_index, size_t hash_index) {
    const gavel_local_file *local_file = local_index == 0 ? NULL : &LOCAL_FILES[local_index];
    const gavel_bookkeeping *bk = bk_index == 0 ? NULL : &BOOKKEEPING[bk_index];
    const char *local_hash = HASHES[hash_index];
    gavel_sync_action got;
    gavel_sync_action want;
    const char *problem;

    memset(&got, 0xAB, sizeof(got)); /* poison: every field must be written */
    gavel_compute_sync_action(local_file, saves, save_count, bk, DEVICE_ID, local_hash, &got);

    problem = well_formed(&got);
    if (problem != NULL) {
        fprintf(stderr, "%s (slot=%zu local=%zu bk=%zu hash=%zu)\n", problem, slot_index, local_index, bk_index,
                hash_index);
        return 0;
    }

    want = oracle_decide(local_file, saves, save_count, bk, DEVICE_ID, local_hash);
    if (!actions_equal(&got, &want)) {
        fprintf(stderr,
                "disagrees with oracle (slot=%zu local=%zu bk=%zu hash=%zu): "
                "got action=%d reason=%d adopt=%d target=%lld/%d server=%lld; "
                "want action=%d reason=%d adopt=%d target=%lld/%d server=%lld\n",
                slot_index, local_index, bk_index, hash_index, (int)got.action, (int)got.reason, got.adopt_baseline,
                (long long)got.target_save_id, got.has_target_save_id, (long long)got.server_save_id, (int)want.action,
                (int)want.reason, want.adopt_baseline, (long long)want.target_save_id, want.has_target_save_id,
                (long long)want.server_save_id);
        return 0;
    }
    return 1;
}

int main(void) {
    gavel_server_save slot[2];
    long checked = 0;

    init_fixtures();

    for (size_t slot_index = 0; slot_index < N_SLOTS; slot_index++) {
        size_t save_count = build_slot(slot_index, slot);
        const gavel_server_save *saves = save_count > 0 ? slot : NULL;
        for (size_t n = 0; n < INNER_COMBINATIONS; n++) {
            size_t local_index = n / (N_BOOKKEEPING * N_HASHES);
            size_t bk_index = (n / N_HASHES) % N_BOOKKEEPING;
            size_t hash_index = n % N_HASHES;
            checked++;
            if (!check_combination(saves, save_count, slot_index, local_index, bk_index, hash_index)) {
                return 1;
            }
        }
    }

    printf("ok: %ld combinations; results well-formed and matching the oracle\n", checked);
    return 0;
}

# Conformance vectors

Language-neutral JSON test vectors: one file per decision-table region, each vector an `{input, expected}` pair. Seeded
from decky-romm-sync's hand-enumerated matrix tests and its property-test corpus.

Format (draft):

```json
{
  "name": "branch6_byte_identical_local_adopts_baseline",
  "input": {
    "local_file": { "filename": "game.srm", "size": 131072, "mtime": 1750000000 },
    "server_saves_in_slot": [
      {
        "id": 42,
        "updated_at": "2026-06-01T12:00:00Z",
        "content_hash": "d41d8cd98f00b204e9800998ecf8427e",
        "device_syncs": []
      }
    ],
    "device_id": "device-a",
    "local_hash": "d41d8cd98f00b204e9800998ecf8427e",
    "baseline": null
  },
  "expected": { "action": "skip", "adopt_baseline": true }
}
```

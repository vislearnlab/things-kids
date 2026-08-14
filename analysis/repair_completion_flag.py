"""Mark the sessions the pagehide-beacon regression un-finished.

Between "Save after every trial" (2026-08-14, 12:01 PT) and the fix later
that afternoon, every adult who finished on Prolific was stored with
complete:false and finishedAt:null. The final save landed; then the browser
navigated to the Prolific completion URL, which fired the pagehide beacon,
which wrote an in-progress payload over it. All 71 trials survived — writes
are cumulative — only the flag was lost.

This does NOT overwrite `complete`. That field records what the client
actually reported, and rewriting it would make an inference indistinguishable
from an observation. It adds a separate `complete_inferred` alongside it, so
analysis can filter on `complete or complete_inferred` and still see which is
which. fetch_data.py surfaces both columns.

A session qualifies only if it ran the full length for its bank (71 adult /
51 child), which is exactly the group whose next timeline step was the
debrief. A genuine mid-session abandonment has fewer trials and is left
alone.

    python3 analysis/repair_completion_flag.py            # dry run
    python3 analysis/repair_completion_flag.py --apply    # write
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

APPLY = "--apply" in sys.argv

# Session lengths come from the manifest that built the banks, not hardcoded
# guesses — if the bank is rebuilt with a different length this stays honest.
manifest = json.loads((ROOT / "public" / "manifest.json").read_text())
meta = manifest.get("meta") or {}
ADULT_N = meta.get("adult_session_length")
CHILD_N = meta.get("session_length")
if not ADULT_N or not CHILD_N:
    raise SystemExit("manifest meta is missing session_length / adult_session_length")

REASON = ("finished all trials; complete flag was overwritten by the pagehide "
          "beacon regression (client fixed 2026-08-14)")

client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
coll = client[os.environ.get("DATABASE", "things_kids")][os.environ.get("COLLECTION", "trials")]

# complete:true records are already correct. Docs with no `complete` field at
# all predate the per-trial save entirely and set finishedAt the old way.
candidates = list(coll.find(
    {"complete": False, "participantID": {"$not": {"$regex": "^__"}}},
    {"participantID": 1, "study": 1, "n_trials": 1, "assigned_bank": 1,
     "complete": 1, "complete_inferred": 1, "updatedAt": 1, "finishedAt": 1},
))

repaired, skipped = [], []
for d in candidates:
    full = ADULT_N if d.get("assigned_bank") == "adult" else CHILD_N
    n = d.get("n_trials") or 0
    (repaired if n >= full else skipped).append((d, n, full))

print(f"{len(candidates)} sessions stored as complete:false")
print(f"  {len(repaired)} ran a full session -> mark complete_inferred")
print(f"  {len(skipped)} genuine partial sessions -> left alone\n")

for d, n, full in repaired:
    already = " (already flagged)" if d.get("complete_inferred") else ""
    print(f"  REPAIR  {d['participantID']:<26} {d.get('study','?'):<22} "
          f"{n}/{full} trials  updatedAt={d.get('updatedAt')}{already}")
for d, n, full in skipped:
    print(f"  skip    {d['participantID']:<26} {d.get('study','?'):<22} {n}/{full} trials")

if not APPLY:
    print("\nDry run. Re-run with --apply to write.")
    sys.exit(0)

stamp = datetime.now(timezone.utc).isoformat()
for d, n, full in repaired:
    coll.update_one({"_id": d["_id"]}, {"$set": {
        "complete_inferred": True,
        "complete_inferred_reason": REASON,
        "complete_inferred_at": stamp,
        # The last write we received is the best available finish time.
        "finishedAt_inferred": d.get("updatedAt"),
    }})
print(f"\nflagged {len(repaired)} sessions at {stamp}")

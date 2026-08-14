"""Replace training_02 in place, without rebuilding the bank.

training_02 was `dessert` (odd) against a pair of `crate` + `forklift`. Those
two are SPoSE-similar — a warehouse association — but they are not the same
kind of thing: crate is a container, forklift is a vehicle. The `condition`
string read "container_vs_food" only because it records the first pair
member's category, which hid the split.

Adults ran it at 0.80 (n=15) where every other training item sits at 0.93-1.00,
and 2 of 3 errors chose forklift — a defensible answer once you notice the
pair is thematic rather than taxonomic. That ambiguity is the phenomenon this
study measures; it does not belong in a trial whose job is to teach the rule.

The replacement pairs `dessert` + `cheese` (both food) against `forklift`
(vehicle): same category, and vis_margin +0.223 — the strongest visual
support of any candidate, so appearance and concept point the same way, which
is what a teaching trial wants. `cheese` comes out of catch_02, and `crate`
takes its place there; catch trials are duplicate-image pop-outs, so the
concept is immaterial (all three run at 1.00). The same 30 concepts are still
spread across the same 11 intro trials with none spanning two of them, so the
no-repeat-within-a-session rule is preserved.

Deliberately a surgical patch, NOT a bank rebuild: rebuilding would
re-randomise every block mid-collection and orphan the sessions already
collected.

    python3 rendering/patch_training_02.py            # dry run
    python3 rendering/patch_training_02.py --apply
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bank as bb  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "public" / "manifest.json"
APPLY = "--apply" in sys.argv

PAIR_A, PAIR_B, ODD = "dessert", "cheese", "forklift"
FREED = "crate"          # takes cheese's place as the catch_02 duplicate

B = bb.Builder()
m = json.loads(MANIFEST.read_text())
intro = m["intro"]


def find(tid):
    for i, t in enumerate(intro):
        if t["trial_id"] == tid:
            return i, t
    raise SystemExit(f"{tid} not found in intro")


i_train, old_train = find("training_02")
i_catch, old_catch = find("catch_02")

# Same field set the builder emits, so the manifest stays homogeneous.
new_train = B.make("training_02", "training",
                   f"{B.cat.get(PAIR_A)}_vs_{B.cat.get(ODD)}",
                   PAIR_A, PAIR_B, ODD)

new_catch = dict(old_catch)
new_catch.update({
    "images": [f"stimuli/{FREED}.jpg", f"stimuli/{FREED}.jpg",
               f"stimuli/{old_catch['odd_concept']}.jpg"],
    "concepts": [FREED, FREED, old_catch["odd_concept"]],
    "pair_concepts": [FREED, FREED],
    "oddity_index": 2,
})

print("training_02")
print(f"  was: {old_train['concepts']}  odd={old_train['odd_concept']}  "
      f"p={old_train['p_correct_spose']}  vis_margin={old_train['vis_margin']}  "
      f"({old_train['pair_category']} + ? vs {old_train['odd_category']})")
print(f"  now: {new_train['concepts']}  odd={new_train['odd_concept']}  "
      f"p={new_train['p_correct_spose']}  vis_margin={new_train['vis_margin']}  "
      f"({new_train['pair_category']} + {B.cat.get(PAIR_B)} vs {new_train['odd_category']})")
print("\ncatch_02")
print(f"  was: {old_catch['concepts']}")
print(f"  now: {new_catch['concepts']}")

# The invariant that matters is per-session, not per-trial: a concept may
# repeat WITHIN a catch trial (that is the pop-out), but must not appear in
# two different intro trials, since every participant sees all of them.
patched = [new_train if i == i_train else new_catch if i == i_catch else t
           for i, t in enumerate(intro)]
owner = {}
clashes = []
for t in patched:
    for c in set(t["concepts"]):
        if c in owner:
            clashes.append(f"{c} in both {owner[c]} and {t['trial_id']}")
        owner[c] = t["trial_id"]
print(f"\nno concept spans two intro trials: {not clashes}"
      + ("".join(f"\n  CLASH {c}" for c in clashes) if clashes else ""))
print(f"distinct intro concepts: {len(owner)} "
      f"(was {len({c for t in intro for c in t['concepts']})})")
missing = [c for c in owner if not (ROOT / "public" / f"stimuli/{c}.jpg").exists()]
print(f"all images present: {not missing}" + (f"  MISSING {missing}" if missing else ""))

if not APPLY:
    print("\nDry run. Re-run with --apply to write manifest.json.")
    sys.exit(0)

intro[i_train] = new_train
intro[i_catch] = new_catch
MANIFEST.write_text(json.dumps(m))
print(f"\nwrote {MANIFEST}")

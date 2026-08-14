"""What the adult data says so far.

Joins the trial-level pull from Mongo to the stimulus covariates in the
manifest (SPoSE predicted difficulty, pairwise SPoSE similarity, CLIP visual
similarity) and reports:

  1. who counts as a usable session, and why the others don't
  2. accuracy and RT by tier — the design's own sanity checks
  3. whether item difficulty tracks the SPoSE prediction the bank was built on
  4. how far the rotating bank has actually been covered, and what that
     implies for how many more adults are needed

Run:  python3 analysis/fetch_data.py && python3 analysis/adult_summary.py
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "analysis" / "data"

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

# A Prolific id is 24 hex characters. Everything else in this collection —
# kid_*, deploy_*, livesave_*, {{%PROLIFIC_PID%}} — is a probe or a pilot.
PROLIFIC_ID = re.compile(r"^[0-9a-f]{24}$")

sessions = pd.read_csv(DATA / "sessions.csv")
trials = pd.read_csv(DATA / "trials.csv")

# ---------- stimulus covariates from the manifest ----------
manifest = json.loads((ROOT / "public" / "manifest.json").read_text())
rows, membership = [], {}
for key in ("intro", "core", "blocks", "adult_blocks"):
    for item in manifest.get(key) or []:
        group = item if isinstance(item, list) else [item]
        for t in group:
            membership.setdefault(t["trial_id"], set()).add(key)
            rows.append({
                "trial_id": t["trial_id"],
                "m_tier": t.get("tier"),
                "condition": t.get("condition"),
                "p_correct_spose": t.get("p_correct_spose"),
                "spose_sim_pair": t.get("spose_sim_pair"),
                "vis_sim_pair": t.get("vis_sim_pair"),
                "vis_margin": t.get("vis_margin"),
                "odd_concept": t.get("odd_concept"),
                "odd_category": t.get("odd_category"),
                "pair_category": t.get("pair_category"),
            })
items = pd.DataFrame(rows).drop_duplicates("trial_id").set_index("trial_id")
items["in_adult_bank"] = [
    "adult_blocks" in membership[i] or bool({"intro", "core"} & membership[i])
    for i in items.index
]
meta = manifest["meta"]

print("=" * 78)
print("1. SESSIONS")
print("=" * 78)
sessions["is_prolific"] = sessions.participantID.astype(str).str.match(PROLIFIC_ID)
sessions["finished"] = (sessions.complete.fillna(False).astype(bool)
                        | sessions.complete_inferred.fillna(False).astype(bool)
                        | sessions.finishedAt.notna())
usable = sessions[sessions.is_prolific & sessions.qa_pass.fillna(False) & sessions.finished]
excluded = sessions[~sessions.participantID.isin(usable.participantID)]

print(f"\n{len(usable)} usable Prolific adults "
      f"(of {int(sessions.is_prolific.sum())} real Prolific sessions, "
      f"{len(sessions)} docs total)\n")
print(usable[["participantID", "n_trials", "n_correct", "mean_rt",
              "training_acc", "catch_acc", "overall_acc"]].to_string(index=False))

print("\nexcluded:")
for _, r in excluded.iterrows():
    why = ("probe / smoke test" if not r.is_prolific and str(r.study) == "deploy_smoke_test"
           else "in-lab pilot on the child bank" if str(r.study) == "things_kids_adult_pilot"
           else "no valid Prolific id (our own test session)" if not r.is_prolific
           else "failed QA" if not bool(r.qa_pass) else "unfinished")
    flags = [c.replace("qa_", "") for c in sessions.columns
             if c.startswith("qa_") and c != "qa_pass" and bool(r.get(c))]
    print(f"  {str(r.participantID)[:26]:<26} {str(r.study):<24} "
          f"{int(r.n_trials):>3} trials  {why}"
          + (f"  [{', '.join(flags)}]" if flags else ""))

d = trials[trials.participantID.isin(usable.participantID)].join(
    items, on="trial_id", rsuffix="_m")
print(f"\n{len(d)} usable trials from {d.participantID.nunique()} adults")

# ---------- 2. by tier ----------
print("\n" + "=" * 78)
print("2. ACCURACY AND RT BY TIER")
print("=" * 78)


def wilson(k, n, z=1.96):
    """Binomial CI that behaves at the ceiling, where these data live."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (max(0.0, c - h), min(1.0, c + h))


by_tier = []
for tier, g in d.groupby("tier"):
    k, n = int(g.correct.sum()), len(g)
    lo, hi = wilson(k, n)
    by_tier.append({"tier": tier, "n_trials": n, "acc": k / n,
                    "ci_lo": lo, "ci_hi": hi,
                    "median_rt": g.rt.median(), "n_items": g.trial_id.nunique()})
by_tier = pd.DataFrame(by_tier).sort_values("acc", ascending=False)
print("\n" + by_tier.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

k, n = int(d.correct.sum()), len(d)
lo, hi = wilson(k, n)
print(f"\noverall: {k}/{n} = {k/n:.3f}  [95% CI {lo:.3f}, {hi:.3f}]   chance = 0.333")

test = d[d.tier.isin(["familiar", "warmup"])]
k2, n2 = int(test.correct.sum()), len(test)
lo2, hi2 = wilson(k2, n2)
print(f"test trials only (excl. training/catch): {k2}/{n2} = {k2/n2:.3f}  "
      f"[{lo2:.3f}, {hi2:.3f}]")

print("\nper-adult accuracy on test trials:")
pa = (test.groupby("participantID")
          .agg(n=("correct", "size"), acc=("correct", "mean"), median_rt=("rt", "median")))
print(pa.to_string(float_format=lambda x: f"{x:.3f}"))

# ---------- 3. does difficulty track SPoSE? ----------
print("\n" + "=" * 78)
print("3. ITEM DIFFICULTY vs. THE SPoSE PREDICTION THE BANK WAS BUILT ON")
print("=" * 78)

t = test.dropna(subset=["p_correct_spose"])
print(f"\n{t.trial_id.nunique()} distinct test items, {len(t)} observations "
      f"({len(t)/max(t.trial_id.nunique(),1):.2f} per item)")

# Trial-level point-biserial: one row per response, no item-mean smoothing.
if len(t) > 2:
    r = np.corrcoef(t.p_correct_spose, t.correct.astype(float))[0, 1]
    print(f"\ntrial-level r(p_correct_spose, correct) = {r:+.3f}   n = {len(t)}")

    print("\nby predicted-difficulty quartile (SPoSE p_correct):")
    t = t.copy()
    t["bin"] = pd.qcut(t.p_correct_spose, 4, duplicates="drop")
    b = t.groupby("bin", observed=True).agg(
        n=("correct", "size"), items=("trial_id", "nunique"),
        pred=("p_correct_spose", "mean"), obs=("correct", "mean"),
        median_rt=("rt", "median"))
    print(b.to_string(float_format=lambda x: f"{x:.3f}"))

    print("\nhardest items observed (>=2 observations, ranked by observed accuracy):")
    it = (t.groupby("trial_id")
            .agg(n=("correct", "size"), obs=("correct", "mean"),
                 pred=("p_correct_spose", "first"), rt=("rt", "median"),
                 odd=("odd_concept", "first"), cat=("odd_category", "first")))
    it = it[it.n >= 2].sort_values("obs").head(12)
    print(it.to_string(float_format=lambda x: f"{x:.3f}") if len(it)
          else "  (no item has 2+ observations yet — the bank rotates faster than the sample)")

# ---------- 3b. the designed contrast ----------
print("\n" + "=" * 78)
print("3b. VISUAL AGREE vs. VISUAL CONFLICT — the contrast the design rests on")
print("=" * 78)

cond = d[d.condition_m.isin(["visual_agree", "visual_conflict"])]
print()
print(cond.groupby("condition_m").agg(
    n=("correct", "size"), items=("trial_id", "nunique"),
    acc=("correct", "mean"), median_rt=("rt", "median")).to_string(
        float_format=lambda x: f"{x:.3f}"))

wide = cond.pivot_table(index="participantID", columns="condition_m",
                        values="correct", aggfunc="mean")
wide["cost"] = wide.visual_agree - wide.visual_conflict
print("\nper adult (each sees 30 of each — the split is balanced by design):")
print(wide.to_string(float_format=lambda x: f"{x:+.3f}"))
same = int((wide.cost > 0).sum())
print(f"\n{same} of {len(wide)} adults are more accurate when appearance agrees "
      f"(mean cost {wide.cost.mean():.3f})")
print("Children should show a LARGER cost if they weight appearance more heavily;\n"
      "that gap is the developmental prediction, and adults are not at ceiling on\n"
      "conflict items, so there is room to see it.")

# ---------- 4. coverage ----------
print("\n" + "=" * 78)
print("4. BANK COVERAGE")
print("=" * 78)

adult_pool = items[items.in_adult_bank]
seen = d.trial_id.unique()
per_item = d.groupby("trial_id").size()
active_adult_items = set()
for b in (manifest.get("adult_blocks") or [])[:meta["active_adult_blocks"]]:
    active_adult_items.update(x["trial_id"] for x in b)
for key in ("intro", "core"):
    active_adult_items.update(x["trial_id"] for x in manifest.get(key) or [])

print(f"\nadult session = {meta['adult_session_length']} trials "
      f"= intro({len(manifest['intro'])}) + core({len(manifest['core'])}) "
      f"+ one of {meta['active_adult_blocks']} active blocks "
      f"({meta['adult_block_n']} trials each)")
print(f"reachable adult items: {len(active_adult_items)}   "
      f"seen at least once: {len(set(seen) & active_adult_items)}   "
      f"({len(set(seen) & active_adult_items)/len(active_adult_items):.0%})")
print(f"observations per seen item: "
      f"min {per_item.min()}, median {per_item.median():.0f}, max {per_item.max()}")

blocks_done = usable.assigned_block.value_counts().to_dict() if "assigned_block" in usable else {}
print(f"\nblocks drawn so far: {blocks_done or '(not in sessions.csv)'}")

core_n = len(manifest["core"]) + len(manifest["intro"])
per_adult_block = meta["adult_block_n"]
for target in (5, 10, 20):
    need = int(np.ceil(target * meta["active_adult_blocks"]))
    print(f"  to reach ~{target:>2} adults per rotating item: ~{need} usable adults "
          f"(core/intro items hit {target * meta['active_adult_blocks']}x over)")

# ---------- 5. the in-lab pilots, for the child bank ----------
pilots = sessions[sessions.study == "things_kids_adult_pilot"]
if len(pilots):
    print("\n" + "=" * 78)
    print("5. IN-LAB ADULT PILOTS (child bank, 51 trials) — kept separate")
    print("=" * 78)
    pd_ = trials[trials.participantID.isin(pilots.participantID)].join(
        items, on="trial_id", rsuffix="_m")
    pt = pd_[pd_.tier.isin(["familiar", "warmup"])]
    for pid, g in pt.groupby("participantID"):
        k, n = int(g.correct.sum()), len(g)
        lo, hi = wilson(k, n)
        print(f"  {pid:<16} {k}/{n} = {k/n:.3f} [{lo:.3f}, {hi:.3f}] "
              f"on child-bank test trials, median RT {g.rt.median():.0f} ms")
    if len(pt):
        tt = pt.dropna(subset=["p_correct_spose"])
        if len(tt) > 2:
            r = np.corrcoef(tt.p_correct_spose, tt.correct.astype(float))[0, 1]
            print(f"  trial-level r(p_correct_spose, correct) = {r:+.3f}  n = {len(tt)}")

print()

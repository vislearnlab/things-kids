"""Simulate developmental data for the THINGS-Kids oddity task, then check
what the design can and cannot recover.

THIS IS SIMULATED DATA. No child has run this task. The point is to find out,
before collecting anything, whether the visual_agree / visual_conflict
crossing can actually identify a developmental shift in how children weight
visual versus conceptual similarity — and how many children it would take.

Generative model
----------------
A child sees a triplet (x0, x1, x2). For each item i, the "pair" is the other
two, and the child scores how well that pair coheres:

    score_i = (1 - w) * z_spose(pair) + w * z_clip(pair)

where z_* are the globally standardised conceptual and visual similarity
matrices, and `w` is that child's weight on visual similarity. The child then
picks the odd item by softmax over the three scores, with inverse temperature
beta, and lapses (picks uniformly at random) with probability `lapse`.

Two things move with age, both taken from the developmental literature on the
perceptual-to-taxonomic shift rather than fitted to anything:

    w(age)      falls from ~.75 at age 3 to ~.20 at age 10 (logistic, centred
                at 6.5 — the shift is usually placed around 5-7)
    lapse(age)  falls from ~.28 at age 3 to ~.03 at age 10 (attention)

beta is held constant across age on purpose. If discriminability also grew
with age it would trade off against w in fitting, and the recovery analysis
below would not be interpretable.

Run:  python3 analysis/simulate_development.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
DERIVED = ROOT / "rendering" / "_derived"
OUT = ROOT / "analysis" / "sim_results.json"

AGES = list(range(3, 11))
N_PER_AGE = 25
N_ACTIVE_BLOCKS = 10
BETA = 2.6
SEED = 11

# Age trajectories.
W_YOUNG, W_OLD, W_CENTRE, W_SLOPE = 0.78, 0.18, 6.5, 0.9
LAPSE_YOUNG, LAPSE_OLD, LAPSE_TAU = 0.28, 0.03, 3.0


def w_of_age(age):
    """Weight on visual similarity: high early, falling through the shift."""
    return W_OLD + (W_YOUNG - W_OLD) / (1 + np.exp(W_SLOPE * (age - W_CENTRE)))


def lapse_of_age(age):
    return LAPSE_OLD + (LAPSE_YOUNG - LAPSE_OLD) * np.exp(-(age - 3) / LAPSE_TAU)


def load_spaces():
    clip = np.load(DERIVED / "clip_image_sim.npy")
    names = json.loads((DERIVED / "clip_concepts.json").read_text())
    cidx = {n: i for i, n in enumerate(names)}
    ids = (RAW / "unique_id.txt").read_text().splitlines()
    sidx = {u: i for i, u in enumerate(ids)}
    spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]

    # Standardise both spaces over the concepts actually in play so the
    # mixture weight `w` means the same thing on both sides.
    def z(mat, index, keys):
        ii = [index[k] for k in keys]
        sub = mat[np.ix_(ii, ii)]
        off = sub[~np.eye(len(ii), dtype=bool)]
        return (sub - off.mean()) / off.std()

    return clip, cidx, spose, sidx, z


def build_trial_table():
    """Read the banked manifest: intro + core + blocks. Core trials are seen
    by every child (the age-trajectory analysis uses these); block trials
    rotate (the item-level benchmark analysis uses these)."""
    man = json.loads((ROOT / "public" / "manifest.json").read_text())
    if "trials" in man:                       # legacy flat manifest
        test = [t for t in man["trials"] if t["tier"] == "familiar"]
        blocks = []
    else:
        test = list(man.get("core", []))
        blocks = man.get("blocks", [])[: man.get("meta", {}).get("active_blocks", 10)]
        for blk in blocks:
            test = test + list(blk)
    clip, cidx, spose, sidx, z = load_spaces()

    keys = sorted({c for t in test for c in t["concepts"]})
    Z_CLIP = z(clip, cidx, keys)
    Z_SPOSE = z(spose, sidx, keys)
    k = {n: i for i, n in enumerate(keys)}

    rows = []
    for t in test:
        cs = t["concepts"]
        # For each candidate odd item, the coherence of the remaining pair.
        pair_spose, pair_clip = [], []
        for i in range(3):
            a, b = [cs[j] for j in range(3) if j != i]
            pair_spose.append(Z_SPOSE[k[a], k[b]])
            pair_clip.append(Z_CLIP[k[a], k[b]])
        rows.append({
            "is_core": t["trial_id"].startswith("core"),
            "block": (None if t["trial_id"].startswith("core")
                      else int(t["trial_id"][3:5])),
            "trial_id": t["trial_id"],
            "condition": t["condition"],
            "difficulty_bin": t["difficulty_bin"],
            "p_spose": t["p_correct_spose"],
            "vis_margin": t["vis_margin"],
            "correct": t["oddity_index"],
            "pair_spose": np.array(pair_spose),
            "pair_clip": np.array(pair_clip),
        })
    return rows


def choice_probs(row, w, beta):
    score = (1 - w) * row["pair_spose"] + w * row["pair_clip"]
    e = np.exp(beta * (score - score.max()))
    return e / e.sum()


def simulate(rows, rng):
    recs = []
    for age in AGES:
        for s in range(N_PER_AGE):
            sid = f"sim_{age:02d}_{s:02d}"
            # Between-child variability around the age trajectory.
            w = float(np.clip(w_of_age(age) + rng.normal(0, 0.10), 0.01, 0.99))
            lapse = float(np.clip(lapse_of_age(age) + rng.normal(0, 0.03), 0.0, 0.6))
            my_block = rng.integers(0, N_ACTIVE_BLOCKS)
            for r in rows:
                if not r["is_core"] and r["block"] != my_block:
                    continue
                p = choice_probs(r, w, BETA)
                p = (1 - lapse) * p + lapse / 3.0
                pick = rng.choice(3, p=p)
                recs.append({
                    "subject": sid, "age": age, "true_w": w, "true_lapse": lapse,
                    "is_core": r["is_core"], "block": r["block"],
                    "trial_id": r["trial_id"], "condition": r["condition"],
                    "difficulty_bin": r["difficulty_bin"], "p_spose": r["p_spose"],
                    "vis_margin": r["vis_margin"],
                    "correct": int(pick == r["correct"]),
                })
    return pd.DataFrame(recs)


def fit_w(subject_df, rows_by_id):
    """Recover one child's visual weight by maximum likelihood, holding beta
    and lapse at their generating values. Tests whether the design can read
    `w` back out of the choices at all."""
    lapse = float(subject_df["true_lapse"].iloc[0])
    obs = subject_df.set_index("trial_id")["correct"].to_dict()

    def nll(w):
        w = float(np.clip(w, 1e-3, 1 - 1e-3))
        tot = 0.0
        for tid, hit in obs.items():
            r = rows_by_id[tid]
            p = choice_probs(r, w, BETA)
            p = (1 - lapse) * p + lapse / 3.0
            pc = p[r["correct"]]
            tot -= np.log(pc if hit else max(1 - pc, 1e-9))
        return tot

    return float(minimize_scalar(nll, bounds=(0.01, 0.99), method="bounded").x)


def main():
    rng = np.random.default_rng(SEED)
    rows = build_trial_table()
    rows_by_id = {r["trial_id"]: r for r in rows}
    print(f"{len(rows)} test trials, {len(AGES)*N_PER_AGE} simulated children")

    df = simulate(rows, rng)
    print(f"{len(df):,} simulated responses")

    out = {"meta": {
        "simulated": True, "n_children": len(AGES) * N_PER_AGE,
        "n_trials": len(rows), "n_responses": len(df),
        "ages": AGES, "n_per_age": N_PER_AGE, "beta": BETA,
    }}

    # 1. Accuracy by age x condition — the headline interaction.
    core_df = df[df.is_core]
    acc = (core_df.groupby(["age", "condition"])["correct"]
             .agg(["mean", "sem", "count"]).reset_index())
    out["acc_by_age_condition"] = acc.to_dict("records")
    piv = acc.pivot(index="age", columns="condition", values="mean")
    piv["gap"] = piv["visual_agree"] - piv["visual_conflict"]
    print("\nage   agree  conflict   gap")
    for a in AGES:
        print(f" {a:>2}   {piv.loc[a,'visual_agree']:.3f}   "
              f"{piv.loc[a,'visual_conflict']:.3f}   {piv.loc[a,'gap']:+.3f}")
    out["gap_by_age"] = [{"age": int(a), "gap": float(piv.loc[a, "gap"])} for a in AGES]

    # 2. Parameter recovery: can we read each child's visual weight back out?
    rec = []
    for sid, sub in core_df.groupby("subject"):
        rec.append({"subject": sid, "age": int(sub["age"].iloc[0]),
                    "true_w": float(sub["true_w"].iloc[0]),
                    "fit_w": fit_w(sub, rows_by_id)})
    rec = pd.DataFrame(rec)
    r_rec = float(rec["true_w"].corr(rec["fit_w"]))
    print(f"\nparameter recovery r(true w, fitted w) = {r_rec:.3f}")
    out["recovery"] = {"r": r_rec, "points": rec.to_dict("records")}
    out["w_by_age"] = [{"age": int(a),
                        "true_w": float(w_of_age(a)),
                        "fit_w": float(rec.loc[rec.age == a, "fit_w"].mean()),
                        "fit_sem": float(rec.loc[rec.age == a, "fit_w"].sem())}
                       for a in AGES]

    # 3. Item difficulty: do young and old children find the same items hard?
    young = core_df[core_df.age <= 5].groupby("trial_id")["correct"].mean()
    old = core_df[core_df.age >= 8].groupby("trial_id")["correct"].mean()
    item = pd.DataFrame({"young": young, "old": old}).join(
        pd.DataFrame([{"trial_id": r["trial_id"], "condition": r["condition"],
                       "p_spose": r["p_spose"], "vis_margin": r["vis_margin"]}
                      for r in rows]).set_index("trial_id"))
    r_item = float(item["young"].corr(item["old"]))
    r_item_agree = float(item[item.condition == "visual_agree"]["young"]
                         .corr(item[item.condition == "visual_agree"]["old"]))
    r_item_conf = float(item[item.condition == "visual_conflict"]["young"]
                        .corr(item[item.condition == "visual_conflict"]["old"]))
    print(f"item difficulty r(young 3-5, old 8-10) = {r_item:.3f}  "
          f"(agree {r_item_agree:.3f} / conflict {r_item_conf:.3f})")
    out["item_agreement"] = {
        "r_all": r_item, "r_agree": r_item_agree, "r_conflict": r_item_conf,
        "points": item.reset_index().to_dict("records"),
    }

    # 4. Power for the age x condition interaction, against a real null.
    # The earlier version only asked whether the gap-vs-age slope was
    # negative, which is ~50% under the null and saturates instantly — it
    # measured nothing. This resamples n children per age, then permutes the
    # age labels to build a null slope distribution and takes a two-sided p.
    powers = []
    core_only = core_df
    subs = (core_only[["subject", "age"]].drop_duplicates()
            .groupby("age")["subject"].apply(list).to_dict())

    def gap_slope(d):
        piv = d.groupby(["age", "condition"])["correct"].mean().unstack()
        if piv.shape[0] < len(AGES) or piv.isna().any().any():
            return np.nan
        gap = (piv["visual_agree"] - piv["visual_conflict"]).values
        return np.polyfit(piv.index.values.astype(float), gap, 1)[0]

    for n in [4, 6, 8, 10, 15, 20, 25]:
        hits, reps = 0, 200
        for _ in range(reps):
            pick = [s_ for a in AGES
                    for s_ in rng.choice(subs[a], size=min(n, len(subs[a])), replace=False)]
            d = core_only[core_only.subject.isin(pick)]
            obs = gap_slope(d)
            if np.isnan(obs):
                continue
            # Null: subject-level age labels shuffled, so any age structure
            # in the gap is destroyed but everything else is preserved.
            null = []
            sub_ages = d[["subject", "age"]].drop_duplicates()
            for _ in range(60):
                perm = sub_ages.copy()
                perm["age"] = rng.permutation(perm["age"].values)
                dd = d.drop(columns="age").merge(perm, on="subject")
                v = gap_slope(dd)
                if not np.isnan(v):
                    null.append(v)
            if not null:
                continue
            pval = (np.sum(np.abs(null) >= abs(obs)) + 1) / (len(null) + 1)
            hits += int(pval < 0.05)
        powers.append({"n_per_age": n, "power": hits / reps,
                       "total_usable": n * len(AGES)})
        print(f"  n={n:>2}/age (N={n*len(AGES):>3})  power = {hits/reps:.2f}")
    out["power"] = powers

    OUT.write_text(json.dumps(out, indent=1, default=float))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

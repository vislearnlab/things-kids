"""How many children does the rotating-bank design need at a museum kiosk?

Two goals need different sample sizes, and the binding one is not obvious:

  A. BENCHMARK  — per-item difficulty measured well enough that correlating it
     against a model's predictions is not mostly noise. Criterion here is
     split-half reliability of the item-difficulty vector, since a benchmark's
     ceiling on model-human correlation is sqrt(reliability).

  B. TRAJECTORY — the age x condition interaction (the agree/conflict gap
     narrowing with age).

Rotation means each item is seen by only n_children * trials_per_child /
bank_size children, so bank size trades directly against per-item precision.

Kiosk realities applied: not every child who starts finishes, and some
sessions are excluded outright.

THIS IS SIMULATION. Rates below are assumptions, flagged as such.

Run:  python3 analysis/kiosk_sample_size.py
"""

import json
import math
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
DERIVED = ROOT / "rendering" / "_derived"

BANK_SIZE = 400
TRIALS_PER_CHILD = 40
AGES = list(range(3, 11))

# --- kiosk assumptions (calibrate against your own CDM records) ---
P_COMPLETE = 0.75        # fraction who finish enough trials to use
P_EXCLUDE = 0.10         # of completers, excluded on catch/attention rules
USABLE_RATE = P_COMPLETE * (1 - P_EXCLUDE)

# Age bands for which item difficulty is estimated separately. Benchmarking
# "which age does this model resemble" needs item difficulty *within* band,
# which divides the sample.
BANDS = {"3-5": [3, 4, 5], "6-7": [6, 7], "8-10": [8, 9, 10]}

BETA = 2.6
W_YOUNG, W_OLD, W_CENTRE, W_SLOPE = 0.78, 0.18, 6.5, 0.9
LAPSE_YOUNG, LAPSE_OLD, LAPSE_TAU = 0.28, 0.03, 3.0

RNG = np.random.default_rng(5)


def w_of_age(a):
    return W_OLD + (W_YOUNG - W_OLD) / (1 + np.exp(W_SLOPE * (a - W_CENTRE)))


def lapse_of_age(a):
    return LAPSE_OLD + (LAPSE_YOUNG - LAPSE_OLD) * np.exp(-(a - 3) / LAPSE_TAU)


def build_bank():
    """A BANK_SIZE bank of triplets spanning the difficulty gradient, half
    visual-agree and half visual-conflict, drawn from the paper concepts."""
    clip = np.load(DERIVED / "clip_image_sim.npy")
    names = json.loads((DERIVED / "clip_concepts.json").read_text())
    ci = {n: i for i, n in enumerate(names)}
    ids = (RAW / "unique_id.txt").read_text().splitlines()
    si = {u: i for i, u in enumerate(ids)}
    spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]
    emb = np.loadtxt(RAW / "spose_embedding_66d.txt")

    pool = [n for n in names if n in si]
    zc = clip.copy()
    off = zc[~np.eye(len(zc), dtype=bool)]
    zc = (zc - off.mean()) / off.std()
    ss = spose.copy()
    offs = ss[~np.eye(len(ss), dtype=bool)]
    zs = (ss - offs.mean()) / offs.std()

    bank = []
    tries = 0
    while len(bank) < BANK_SIZE and tries < 400_000:
        tries += 1
        a, b, c = RNG.choice(len(pool), 3, replace=False)
        a, b, c = pool[a], pool[b], pool[c]
        if spose[si[a], si[b]] < 0.70:
            continue
        sab = float(emb[si[a]] @ emb[si[b]])
        sac = float(emb[si[a]] @ emb[si[c]])
        sbc = float(emb[si[b]] @ emb[si[c]])
        mx = max(sab, sac, sbc)
        p = math.exp(sab - mx) / sum(math.exp(x - mx) for x in (sab, sac, sbc))
        if not (0.40 <= p < 0.95):
            continue
        vm = float(clip[ci[a], ci[b]] - max(clip[ci[a], ci[c]], clip[ci[b], ci[c]]))
        cond = "agree" if vm >= 0.03 else ("conflict" if vm <= -0.01 else None)
        if cond is None:
            continue
        # Pair coherence for each candidate odd item, in both spaces.
        ps, pc = [], []
        for i, (x, y) in enumerate([(b, c), (a, c), (a, b)]):
            ps.append(zs[si[x], si[y]])
            pc.append(zc[ci[x], ci[y]])
        bank.append({"cond": cond, "p_spose": p,
                     "pair_spose": np.array(ps), "pair_clip": np.array(pc),
                     "correct": 2})
    return bank


def simulate(bank, n_children):
    """Each child gets a random TRIALS_PER_CHILD subset of the bank."""
    n_items = len(bank)
    hits = np.zeros((n_children, n_items))
    seen = np.zeros((n_children, n_items), dtype=bool)
    ages = np.array([AGES[i % len(AGES)] for i in range(n_children)])
    for s in range(n_children):
        w = float(np.clip(w_of_age(ages[s]) + RNG.normal(0, 0.10), .01, .99))
        lp = float(np.clip(lapse_of_age(ages[s]) + RNG.normal(0, .03), 0, .6))
        which = RNG.choice(n_items, TRIALS_PER_CHILD, replace=False)
        for it in which:
            r = bank[it]
            score = (1 - w) * r["pair_spose"] + w * r["pair_clip"]
            e = np.exp(BETA * (score - score.max()))
            p = e / e.sum()
            p = (1 - lp) * p + lp / 3.0
            hits[s, it] = int(RNG.choice(3, p=p) == r["correct"])
            seen[s, it] = True
    return hits, seen, ages


def split_half_reliability(hits, seen, reps=25):
    """Correlate item difficulty from two random halves of the children,
    Spearman-Brown corrected up to the full sample."""
    n = hits.shape[0]
    out = []
    for _ in range(reps):
        perm = RNG.permutation(n)
        h1, h2 = perm[: n // 2], perm[n // 2:]
        d = []
        for half in (h1, h2):
            s = seen[half].sum(0)
            acc = np.where(s > 0, hits[half].sum(0) / np.maximum(s, 1), np.nan)
            d.append(acc)
        ok = ~np.isnan(d[0]) & ~np.isnan(d[1]) & (seen[h1].sum(0) >= 3) & (seen[h2].sum(0) >= 3)
        if ok.sum() < 20:
            continue
        r = np.corrcoef(d[0][ok], d[1][ok])[0, 1]
        out.append(2 * r / (1 + r))          # Spearman-Brown
    return float(np.nanmean(out)) if out else np.nan


def main():
    bank = build_bank()
    print(f"bank: {len(bank)} triplets "
          f"({sum(b['cond']=='agree' for b in bank)} agree / "
          f"{sum(b['cond']=='conflict' for b in bank)} conflict)")
    print(f"each child sees {TRIALS_PER_CHILD}; "
          f"so each item is seen by n_children x {TRIALS_PER_CHILD/len(bank):.2f}\n")

    print(f"{'usable N':>9} {'per item':>9} {'reliability':>12}  {'model-r ceiling':>15}")
    results = []
    for n in [100, 200, 300, 500, 750, 1000, 1500]:
        hits, seen, ages = simulate(bank, n)
        rel = split_half_reliability(hits, seen)
        per_item = seen.sum(0).mean()
        ceiling = math.sqrt(max(rel, 0)) if not np.isnan(rel) else float("nan")
        results.append((n, per_item, rel, ceiling))
        print(f"{n:>9} {per_item:>9.1f} {rel:>12.3f}  {ceiling:>15.3f}")

    # What usable N clears reliability .8 overall?
    target = 0.80
    need = next((n for n, _, rel, _ in results if rel >= target), None)
    print(f"\nreliability >= {target}: usable N ~ {need}")

    # Within age band, the sample is divided.
    print("\nIf item difficulty must be estimated WITHIN age band:")
    for band, yrs in BANDS.items():
        share = len(yrs) / len(AGES)
        print(f"  band {band:<5} is {share:.0%} of the sample -> "
              f"needs ~{math.ceil(need/share/50)*50} usable to give that band {need}")
    worst = math.ceil(need / (min(len(v) for v in BANDS.values()) / len(AGES)) / 50) * 50
    print(f"  binding requirement: ~{worst} usable children")

    print(f"\nRecruitment, at {USABLE_RATE:.0%} usable "
          f"({P_COMPLETE:.0%} finish x {1-P_EXCLUDE:.0%} pass exclusions):")
    for label, target_n in [("benchmark, pooled ages", need),
                            ("benchmark, within age band", worst)]:
        rec = math.ceil(target_n / USABLE_RATE / 50) * 50
        print(f"  {label:<28} {target_n:>5} usable -> ~{rec} children approached")
        for rate in [10, 20, 30]:
            print(f"      at {rate:>2}/testing-day: {rec/rate:>5.0f} days "
                  f"(~{rec/rate/8:.1f} months at 8 days/mo)")


if __name__ == "__main__":
    main()

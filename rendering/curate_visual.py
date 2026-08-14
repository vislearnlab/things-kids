"""Build the visual-similarity oddity trial set.

The construct here is *visual* similarity structure, so trials are selected
with CLIP image embeddings (rendering/clip_visual_sims.py), not SPoSE. On
each trial two images are visually similar and one is visually distant; the
child taps the odd one.

Difficulty is the visual margin

    delta = s(a, b) - max(s(a, c), s(b, c))

i.e. how much more similar the pair is to each other than the odd item is to
either. Small delta = hard. Margin is reported raw rather than converted to a
predicted accuracy: CLIP cosines are compressed (mean .55, max .95) and any
softmax over them needs a temperature that can only be fit to real oddity
data, which does not exist for these items yet. Inventing one would dress up
an uncalibrated guess as a prediction.

Two test conditions dissociate visual from conceptual structure:

  visual_within  - the visually similar pair is also same-category, so visual
                   and conceptual similarity agree.
  visual_cross   - the visually similar pair spans different categories, so
                   only visual structure supports the grouping. This is the
                   diagnostic condition.

Every concept comes from the vocab-gradient published item set (test_items.csv
targets + distractors), so oddity data joins to the paper's 4AFC item data.

Outputs (overwrites):
    public/stimuli/<trial_id>/{0,1,2}.jpg
    public/manifest.json

Run:  python3 rendering/curate_visual.py
"""

import json
import math
import random
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
DERIVED = ROOT / "rendering" / "_derived"
VG = Path("/Users/brialong/Documents/GitHub/vocab-gradient")

IMAGE_DIR = VG / "stimuli" / "3_selected_stimuli" / "images_final2023-11-09"
CONCEPTS_TSV = VG / "data" / "item_metadata" / "things_concepts.tsv"
TEST_ITEMS = VG / "data" / "item_metadata" / "test_items.csv"

STIMULI_DIR = ROOT / "public" / "stimuli"
MANIFEST_PATH = ROOT / "public" / "manifest.json"

JPEG_MAX_DIM = 512
JPEG_QUALITY = 88

# A pair must be genuinely visually similar to read as "these two go together".
# .736 is the 99th percentile of the pairwise CLIP distribution.
PAIR_VIS_MIN = 0.736
# No two concepts in *different* trials may be this visually similar. Distinct
# THINGS concepts sometimes have near-identical photos (caramel/fudge at .92,
# asparagus/chive at .90) and seeing one after the other reads as the same
# image coming back, even though no image is literally repeated. Concepts
# inside a single trial are exempt — there the pair is *meant* to look alike.
MAX_CROSS_TRIAL_SIM = 0.88
# Training/warmup use only concepts adults reliably name, so the intro trials
# feel friendly. Test trials skip this: the task is visual, and naming is not
# required to judge which image doesn't belong.
KID_KNOWN_THRESHOLD = 0.95
# Every image appears exactly once in the whole experiment. Repeats would let
# a child recognise an image from an earlier trial rather than judge it fresh,
# and would make item effects non-independent across trials.
MAX_USES_PER_CONCEPT = 1

# Difficulty bins on the visual margin.
BINS = [
    ("very hard", 0.00, 0.03),
    ("hard",      0.03, 0.06),
    ("medium",    0.06, 0.10),
    ("easy",      0.10, 0.15),
    ("very easy", 0.15, 0.22),
]
# Test trials per bin, per condition -> 5 bins x 2 conditions x 4 = 40 trials.
PER_BIN_PER_CONDITION = 4
TRAINING_N = 6
WARMUP_N = 6
CATCH_N = 4
TRAINING_MARGIN_MIN = 0.28
WARMUP_MARGIN_MIN = 0.22

RNG = random.Random(20260813)


def load_all():
    sim = np.load(DERIVED / "clip_image_sim.npy")
    names = json.loads((DERIVED / "clip_concepts.json").read_text())
    idx = {n: i for i, n in enumerate(names)}

    df = pd.read_csv(CONCEPTS_TSV, sep="\t")
    df["Percent_known"] = pd.to_numeric(df["Percent_known"], errors="coerce")
    cat_col = "Top-down Category (manual selection)"
    wn_col = "Top-down Category (WordNet)"
    df["top_cat"] = df[cat_col].where(df[cat_col].notna() & (df[cat_col] != ""), df[wn_col])

    cat, known = {}, {}
    for _, r in df.iterrows():
        uid = str(r["uniqueID"])
        if uid not in idx:
            continue
        t = r["top_cat"]
        if isinstance(t, str) and t.strip() and t.strip().lower() != "nan":
            cat[uid] = t.strip().lower().split(",")[0].strip()
        known[uid] = bool(r["Percent_known"] >= KID_KNOWN_THRESHOLD)

    # SPoSE conceptual similarity, carried through as an annotation so the
    # analysis can separate visual from conceptual similarity per trial.
    spose_ids = (RAW / "unique_id.txt").read_text().splitlines()
    spose_idx = {u: i for i, u in enumerate(spose_ids)}
    spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]

    return sim, names, idx, cat, known, spose, spose_idx


def high_sim_pairs(sim, names, idx, restrict=None):
    """All pairs above the visual-similarity floor, most similar first."""
    pool = [n for n in names if restrict is None or n in restrict]
    out = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]
            s = float(sim[idx[a], idx[b]])
            if s >= PAIR_VIS_MIN:
                out.append((a, b, s))
    out.sort(key=lambda x: -x[2])
    return out


def build():
    sim, names, idx, cat, known, spose, spose_idx = load_all()
    print(f"{len(names)} paper concepts with images and CLIP features")
    print(f"  with a top-down category : {len(cat)}")
    print(f"  adult-nameable (>=.95)   : {sum(known.values())}")

    uses = {}
    committed = []          # every concept already placed in some trial

    def can_use(*cs):
        return all(uses.get(c, 0) < MAX_USES_PER_CONCEPT for c in cs)

    def far_enough(*cs):
        """No candidate may look near-identical to anything already placed."""
        return all(float(sim[idx[c], idx[prev]]) < MAX_CROSS_TRIAL_SIM
                   for c in cs for prev in committed)

    def mark(*cs):
        for c in cs:
            uses[c] = uses.get(c, 0) + 1
            committed.append(c)

    def spose_sim(a, b):
        if a in spose_idx and b in spose_idx:
            return round(float(spose[spose_idx[a], spose_idx[b]]), 3)
        return None

    def make(trial_id, tier, condition, a, b, c, margin):
        """Assemble one trial, randomising which slot the odd item occupies."""
        triple = [a, b, c]
        order = [0, 1, 2]
        RNG.shuffle(order)
        shown = [triple[k] for k in order]
        return {
            "trial_id": trial_id,
            "tier": tier,
            "dataset": "vocab_gradient_clip",
            "condition": condition,
            "n_objects": 3,
            "oddity_index": order.index(2),
            "images": [f"stimuli/{trial_id}/{k}.jpg" for k in range(3)],
            "concepts": shown,
            "odd_concept": c,
            "pair_concepts": [a, b],
            "pair_category": cat.get(a),
            "odd_category": cat.get(c),
            "vis_sim_pair": round(float(sim[idx[a], idx[b]]), 3),
            "vis_sim_odd_to_a": round(float(sim[idx[a], idx[c]]), 3),
            "vis_sim_odd_to_b": round(float(sim[idx[b], idx[c]]), 3),
            "vis_margin": round(float(margin), 3),
            "spose_sim_pair": spose_sim(a, b),
            "spose_sim_odd_to_a": spose_sim(a, c),
            "spose_sim_odd_to_b": spose_sim(b, c),
            # No adult oddity data exists for these items yet.
            "human_avg_adult": None,
            "rt_avg_adult": None,
        }

    trials = []
    friendly = {n for n in names if known.get(n) and n in cat}
    categorised = {n for n in names if n in cat}

    def find_third(a, b, s_ab, pool, lo, hi, require_diff_cat=True):
        """A third concept placing the trial's margin inside [lo, hi)."""
        cands = sorted(pool)
        RNG.shuffle(cands)
        for c in cands:
            if c in (a, b) or not can_use(c) or not far_enough(c):
                continue
            # The odd item must not share either pair member's category, so
            # "doesn't belong" is never ambiguous.
            if require_diff_cat and cat.get(c) in (cat.get(a), cat.get(b)):
                continue
            m = s_ab - max(float(sim[idx[a], idx[c]]), float(sim[idx[b], idx[c]]))
            if lo <= m < hi:
                return c, m
        return None

    # ---- test: margin gradient x (within-category, cross-category).
    # Filled hardest-bin-first. With every image used at most once, the tight
    # bins are the scarce ones — letting the easy bins draw first would spend
    # the high-similarity pairs that only the hard bins can use.
    test_pairs = high_sim_pairs(sim, names, idx, restrict=categorised)
    RNG.shuffle(test_pairs)
    counts = {}

    for lbl, lo, hi in BINS:
        for cond in ("visual_within", "visual_cross"):
            made = 0
            for a, b, s_ab in test_pairs:
                if made >= PER_BIN_PER_CONDITION:
                    break
                if not can_use(a, b) or not far_enough(a, b):
                    continue
                same_cat = cat[a] == cat[b]
                if (cond == "visual_within") != same_cat:
                    continue
                found = find_third(a, b, s_ab, categorised, lo, hi)
                if found is None:
                    continue
                c, m = found
                tid = f"test_{cond}_{lbl.replace(' ', '')}_{made:02d}"
                t = make(tid, "familiar", cond, a, b, c, m)
                t["difficulty_bin"] = lbl
                trials.append(t)
                mark(a, b, c)
                made += 1
            counts[(lbl, cond)] = made

    print("test trials:")
    for lbl, _, _ in BINS:
        print(f"  {lbl:<10} within {counts[(lbl,'visual_within')]}  "
              f"cross {counts[(lbl,'visual_cross')]}")

    # ---- training + warmup: obvious trials from nameable, categorised items,
    # drawn after the test set so they never compete for its scarce pairs.
    intro_pairs = high_sim_pairs(sim, names, idx, restrict=friendly)
    RNG.shuffle(intro_pairs)

    for tier, count, floor in (("training", TRAINING_N, TRAINING_MARGIN_MIN),
                               ("warmup", WARMUP_N, WARMUP_MARGIN_MIN)):
        made = 0
        for a, b, s_ab in intro_pairs:
            if made >= count:
                break
            if not can_use(a, b) or not far_enough(a, b):
                continue
            found = find_third(a, b, s_ab, friendly, floor, 9.0)
            if found is None:
                continue
            c, m = found
            tid = f"{tier}_{made:02d}"
            trials.append(make(tid, tier, f"{cat.get(a)}_vs_{cat.get(c)}", a, b, c, m))
            mark(a, b, c)
            made += 1
        print(f"{tier}: {made} trials")

    # ---- catch: the same image twice plus a visually distant one. This is the
    # one deliberate exception to the no-repeats rule — the duplicate is what
    # makes it an attention check rather than a similarity judgement, so a
    # child who is engaged at all cannot miss it. The duplicated concept and
    # its odd item are still used nowhere else in the experiment.
    catch_pool = [n for n in sorted(friendly) if can_use(n)]
    RNG.shuffle(catch_pool)
    made = 0
    for a in catch_pool:
        if made >= CATCH_N:
            break
        if not can_use(a) or not far_enough(a):
            continue
        # Least visually similar available concept — a maximal contrast.
        row = sim[idx[a]].copy()
        order_by_sim = np.argsort(row)
        c = next((names[j] for j in order_by_sim
                  if names[j] != a and can_use(names[j]) and far_enough(names[j])), None)
        if c is None:
            continue
        tid = f"catch_{made:02d}"
        triple = [a, a, c]
        order = [0, 1, 2]
        RNG.shuffle(order)
        shown = [triple[k] for k in order]
        trials.append({
            "trial_id": tid, "tier": "catch", "dataset": "vocab_gradient_clip",
            "condition": "attention_check", "n_objects": 3,
            "oddity_index": order.index(2),
            "images": [f"stimuli/{tid}/{k}.jpg" for k in range(3)],
            "concepts": shown, "odd_concept": c, "pair_concepts": [a, a],
            "duplicate_image": True,
            "vis_sim_pair": 1.0,
            "vis_sim_odd_to_a": round(float(sim[idx[a], idx[c]]), 3),
            "vis_margin": round(1.0 - float(sim[idx[a], idx[c]]), 3),
            "human_avg_adult": None, "rt_avg_adult": None,
        })
        mark(a, c)
        made += 1
    print(f"catch: {made} trials (duplicate-image attention checks)")

    write_stimuli(trials)
    MANIFEST_PATH.write_text(json.dumps({"trials": trials}, indent=2))
    print(f"\n{len(trials)} trials -> {MANIFEST_PATH}")
    return trials


def write_stimuli(trials):
    if STIMULI_DIR.exists():
        shutil.rmtree(STIMULI_DIR)
    STIMULI_DIR.mkdir(parents=True)
    for t in trials:
        d = STIMULI_DIR / t["trial_id"]
        d.mkdir(parents=True, exist_ok=True)
        for k, concept in enumerate(t["concepts"]):
            src = IMAGE_DIR / f"{concept}.jpg"
            im = Image.open(src).convert("RGB")
            im.thumbnail((JPEG_MAX_DIM, JPEG_MAX_DIM), Image.LANCZOS)
            im.save(d / f"{k}.jpg", quality=JPEG_QUALITY)
    print(f"wrote images for {len(trials)} trials -> {STIMULI_DIR}")


if __name__ == "__main__":
    build()

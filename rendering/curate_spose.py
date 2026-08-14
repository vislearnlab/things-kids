"""Build the SPoSE-selected oddity trial set.

Trials are selected with SPoSE conceptual similarity. SPoSE was fit to 4.7M
adult odd-one-out judgements, so its softmax over the three pairwise
similarities is a *calibrated* predicted P(adults pick c as odd) — unlike a
softmax over CLIP cosines, which needs a temperature nobody has fit. That is
why difficulty here is a probability and the CLIP version reported raw margin.

    P(c odd) = exp(s_ab) / [exp(s_ab) + exp(s_ac) + exp(s_bc)]

Visual similarity is crossed in rather than left to a post-hoc regression.
Across the 432 paper concepts, CLIP visual and SPoSE conceptual similarity
correlate r = .49 (r^2 = .24), so they are separable — but a SPoSE-only
selection would still leave visual similarity varying uncontrolled. Each
SPoSE difficulty bin is therefore split by whether CLIP agrees:

  visual_agree     - CLIP also puts c furthest away. Conceptual and visual
                     structure point at the same answer.
  visual_conflict  - CLIP puts c no further away than the pair members are
                     from each other. Only conceptual structure supports the
                     intended answer; visual similarity works against it.

The contrast is the developmental payoff: if younger children weight visual
similarity more heavily, they should fall off specifically on conflict
trials. Every trial also carries its raw CLIP terms, so visual similarity can
additionally be regressed out continuously.

Constraints carried over from the visual build: every image appears exactly
once, no two concepts in different trials look near-identical, and every
concept comes from the vocab-gradient published item set.

Outputs (overwrites):
    public/stimuli/<trial_id>/{0,1,2}.jpg
    public/manifest.json

Run:  python3 rendering/curate_spose.py
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

STIMULI_DIR = ROOT / "public" / "stimuli"
MANIFEST_PATH = ROOT / "public" / "manifest.json"

JPEG_MAX_DIM = 512
JPEG_QUALITY = 88

# The two "go together" items must be genuinely conceptually similar.
PAIR_SPOSE_MIN = 0.70
# No two concepts in *different* trials may look this alike. Distinct THINGS
# concepts sometimes have near-identical photos (caramel/fudge at .92), and
# seeing one after the other reads as the same image coming back. Concepts
# inside one trial are exempt.
MAX_CROSS_TRIAL_SIM = 0.88
# Every image appears exactly once across the whole experiment.
MAX_USES_PER_CONCEPT = 1
KID_KNOWN_THRESHOLD = 0.95

# Difficulty bins on SPoSE-predicted P(adult picks the intended odd item).
# Chance is .33.
BINS = [
    ("very hard", 0.40, 0.55),
    ("hard",      0.55, 0.70),
    ("medium",    0.70, 0.80),
    ("easy",      0.80, 0.90),
    ("very easy", 0.90, 0.95),
]
# CLIP visual margin: how far the vision model leans, and which way.
VIS_AGREE_MIN = 0.03        # CLIP clearly agrees c is the odd one
VIS_CONFLICT_MAX = -0.01    # CLIP leans against the intended answer

PER_BIN_PER_CONDITION = 4   # 5 bins x 2 conditions x 4 = 40 test trials
TRAINING_N = 6
WARMUP_N = 6
CATCH_N = 4
TRAINING_P_MIN = 0.97
WARMUP_P_MIN = 0.93

RNG = random.Random(20260813)


def load_all():
    clip = np.load(DERIVED / "clip_image_sim.npy")
    names = json.loads((DERIVED / "clip_concepts.json").read_text())
    cidx = {n: i for i, n in enumerate(names)}

    spose_ids = (RAW / "unique_id.txt").read_text().splitlines()
    sidx = {u: i for i, u in enumerate(spose_ids)}
    spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]
    emb = np.loadtxt(RAW / "spose_embedding_66d.txt")

    df = pd.read_csv(CONCEPTS_TSV, sep="\t")
    df["Percent_known"] = pd.to_numeric(df["Percent_known"], errors="coerce")
    cat_col = "Top-down Category (manual selection)"
    wn_col = "Top-down Category (WordNet)"
    df["top_cat"] = df[cat_col].where(df[cat_col].notna() & (df[cat_col] != ""), df[wn_col])

    cat, known = {}, {}
    for _, r in df.iterrows():
        uid = str(r["uniqueID"])
        if uid not in cidx:
            continue
        t = r["top_cat"]
        if isinstance(t, str) and t.strip() and t.strip().lower() != "nan":
            cat[uid] = t.strip().lower().split(",")[0].strip()
        known[uid] = bool(r["Percent_known"] >= KID_KNOWN_THRESHOLD)

    # Only concepts present in both spaces are usable.
    usable = [n for n in names if n in sidx]
    return clip, cidx, spose, emb, sidx, usable, cat, known


def build():
    clip, cidx, spose, emb, sidx, usable, cat, known = load_all()
    print(f"{len(usable)} paper concepts in both CLIP and SPoSE")
    print(f"  with a top-down category : {sum(1 for n in usable if n in cat)}")

    def s_concept(a, b):
        return float(spose[sidx[a], sidx[b]])

    def s_visual(a, b):
        return float(clip[cidx[a], cidx[b]])

    def triplet_p(a, b, c):
        """SPoSE-calibrated P(c chosen as odd)."""
        sab = float(emb[sidx[a]] @ emb[sidx[b]])
        sac = float(emb[sidx[a]] @ emb[sidx[c]])
        sbc = float(emb[sidx[b]] @ emb[sidx[c]])
        m = max(sab, sac, sbc)
        z = sum(math.exp(x - m) for x in (sab, sac, sbc))
        return math.exp(sab - m) / z

    def vis_margin(a, b, c):
        """CLIP's opinion: >0 means it agrees c is the odd one."""
        return s_visual(a, b) - max(s_visual(a, c), s_visual(b, c))

    uses, committed = {}, []

    def can_use(*cs):
        return all(uses.get(c, 0) < MAX_USES_PER_CONCEPT for c in cs)

    def far_enough(*cs):
        return all(s_visual(c, prev) < MAX_CROSS_TRIAL_SIM
                   for c in cs for prev in committed)

    def mark(*cs):
        for c in cs:
            uses[c] = uses.get(c, 0) + 1
            committed.append(c)

    def make(trial_id, tier, condition, a, b, c, p, vm):
        triple = [a, b, c]
        order = [0, 1, 2]
        RNG.shuffle(order)
        shown = [triple[k] for k in order]
        return {
            "trial_id": trial_id,
            "tier": tier,
            "dataset": "vocab_gradient_spose",
            "condition": condition,
            "n_objects": 3,
            "oddity_index": order.index(2),
            "images": [f"stimuli/{trial_id}/{k}.jpg" for k in range(3)],
            "concepts": shown,
            "odd_concept": c,
            "pair_concepts": [a, b],
            "pair_category": cat.get(a),
            "odd_category": cat.get(c),
            # Conceptual (selection variable)
            "spose_sim_pair": round(s_concept(a, b), 3),
            "spose_sim_odd_to_a": round(s_concept(a, c), 3),
            "spose_sim_odd_to_b": round(s_concept(b, c), 3),
            "p_correct_spose": round(p, 3),
            # Visual (crossed factor, and available as a continuous covariate)
            "vis_sim_pair": round(s_visual(a, b), 3),
            "vis_sim_odd_to_a": round(s_visual(a, c), 3),
            "vis_sim_odd_to_b": round(s_visual(b, c), 3),
            "vis_margin": round(vm, 3),
            "human_avg_adult": None,
            "rt_avg_adult": None,
        }

    pool = [n for n in usable if n in cat]
    pairs = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]
            if s_concept(a, b) >= PAIR_SPOSE_MIN:
                pairs.append((a, b))
    RNG.shuffle(pairs)
    print(f"{len(pairs)} conceptually similar pairs (SPoSE >= {PAIR_SPOSE_MIN})")

    def find_third(a, b, pool_, p_lo, p_hi, vis_lo, vis_hi, require_diff_cat=True):
        cands = sorted(pool_)
        RNG.shuffle(cands)
        for c in cands:
            if c in (a, b) or not can_use(c) or not far_enough(c):
                continue
            if require_diff_cat and cat.get(c) in (cat.get(a), cat.get(b)):
                continue
            p = triplet_p(a, b, c)
            if not (p_lo <= p < p_hi):
                continue
            vm = vis_margin(a, b, c)
            if not (vis_lo <= vm < vis_hi):
                continue
            return c, p, vm
        return None

    trials = []
    counts = {}

    # ---- test: SPoSE difficulty gradient x CLIP agreement.
    # Hardest bins first — with each image usable once, the tight cells are
    # scarce and must get first claim on the good pairs.
    CONDITIONS = [
        ("visual_agree",    VIS_AGREE_MIN, 9.0),
        ("visual_conflict", -9.0, VIS_CONFLICT_MAX),
    ]
    for lbl, p_lo, p_hi in BINS:
        for cond, v_lo, v_hi in CONDITIONS:
            made = 0
            for a, b in pairs:
                if made >= PER_BIN_PER_CONDITION:
                    break
                if not can_use(a, b) or not far_enough(a, b):
                    continue
                found = find_third(a, b, pool, p_lo, p_hi, v_lo, v_hi)
                if found is None:
                    continue
                c, p, vm = found
                tid = f"test_{cond}_{lbl.replace(' ', '')}_{made:02d}"
                t = make(tid, "familiar", cond, a, b, c, p, vm)
                t["difficulty_bin"] = lbl
                trials.append(t)
                mark(a, b, c)
                made += 1
            counts[(lbl, cond)] = made

    print("test trials (SPoSE difficulty x CLIP agreement):")
    for lbl, _, _ in BINS:
        print(f"  {lbl:<10} agree {counts[(lbl,'visual_agree')]}  "
              f"conflict {counts[(lbl,'visual_conflict')]}")

    # ---- training + warmup: obvious trials, nameable items, drawn after the
    # test set so they never compete for its scarce pairs.
    friendly = [n for n in pool if known.get(n)]
    friendly_pairs = [(a, b) for a, b in pairs if known.get(a) and known.get(b)]

    for tier, count, floor in (("training", TRAINING_N, TRAINING_P_MIN),
                               ("warmup", WARMUP_N, WARMUP_P_MIN)):
        made = 0
        for a, b in friendly_pairs:
            if made >= count:
                break
            if not can_use(a, b) or not far_enough(a, b):
                continue
            found = find_third(a, b, friendly, floor, 1.01, VIS_AGREE_MIN, 9.0)
            if found is None:
                continue
            c, p, vm = found
            tid = f"{tier}_{made:02d}"
            trials.append(make(tid, tier, f"{cat.get(a)}_vs_{cat.get(c)}", a, b, c, p, vm))
            mark(a, b, c)
            made += 1
        print(f"{tier}: {made} trials")

    # ---- catch: same image twice plus a maximally distant one. The one
    # deliberate exception to no-repeats — the duplicate is what makes it an
    # attention check rather than a similarity judgement.
    catch_pool = [n for n in friendly if can_use(n)]
    RNG.shuffle(catch_pool)
    made = 0
    for a in catch_pool:
        if made >= CATCH_N:
            break
        if not can_use(a) or not far_enough(a):
            continue
        order_by_sim = np.argsort(clip[cidx[a]])
        inv = {v: k for k, v in cidx.items()}
        c = next((inv[j] for j in order_by_sim
                  if inv[j] != a and can_use(inv[j]) and far_enough(inv[j])), None)
        if c is None:
            continue
        tid = f"catch_{made:02d}"
        triple, order = [a, a, c], [0, 1, 2]
        RNG.shuffle(order)
        trials.append({
            "trial_id": tid, "tier": "catch", "dataset": "vocab_gradient_spose",
            "condition": "attention_check", "n_objects": 3,
            "oddity_index": order.index(2),
            "images": [f"stimuli/{tid}/{k}.jpg" for k in range(3)],
            "concepts": [triple[k] for k in order],
            "odd_concept": c, "pair_concepts": [a, a],
            "duplicate_image": True,
            "spose_sim_pair": 1.0, "vis_sim_pair": 1.0,
            "vis_sim_odd_to_a": round(s_visual(a, c), 3),
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
            im = Image.open(IMAGE_DIR / f"{concept}.jpg").convert("RGB")
            im.thumbnail((JPEG_MAX_DIM, JPEG_MAX_DIM), Image.LANCZOS)
            im.save(d / f"{k}.jpg", quality=JPEG_QUALITY)
    print(f"wrote images for {len(trials)} trials -> {STIMULI_DIR}")


if __name__ == "__main__":
    build()

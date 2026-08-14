"""Build the balanced item bank: a fixed core plus rotating blocks.

Architecture
------------
Every child does the same CORE_N trials (cross-child comparability, so the
age-trajectory figure works at small N), plus one randomly assigned rotating
BLOCK of BLOCK_N trials (benchmark breadth, accumulating across children).

Rotating items are organised into blocks rather than sampled freely at
runtime, so the no-repeats constraint is guaranteed by construction instead
of by a runtime constraint solver: within any session (core + one block) no
concept appears twice and no two concepts look near-identical. Concepts do
repeat *across* blocks — different children, so no child ever sees a repeat.

Balance
-------
visual_agree and visual_conflict are forced to 50/50 in both the core and
every block. Conflict triplets are genuinely scarcer (visual and conceptual
similarity usually agree), so they are allocated first.

Per-item precision
------------------
Each rotating item is seen by n_children / N_BLOCKS children. With 10 active
blocks and 200 usable children that is 20 per item, which simulation put at
split-half reliability ~.81. Deploy fewer blocks for more precision per item,
more blocks for more breadth. ACTIVE_BLOCKS controls this without rebuilding.

Images are written once per concept to public/stimuli/<concept>.jpg and
shared across trials.

Outputs (overwrites):
    public/stimuli/<concept>.jpg
    public/manifest.json     {core: [...], blocks: [[...], ...], meta: {...}}

Run:  python3 rendering/build_bank.py
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

CORE_N = 20          # fixed trials every child sees
BLOCK_N = 20         # rotating trials per child session
N_BLOCKS = 20        # blocks built (bank = CORE_N + N_BLOCKS * BLOCK_N)
ACTIVE_BLOCKS = 10   # blocks actually served; raise as N grows

# Adults are far faster than children and are here for item coverage, not
# depth, so they get double the rotating trials. Blocks cannot simply be
# doubled up: each child block is drawn from the same ~229-concept pool left
# after core+intro, so any two of them share ~49 of 60 concepts. Adult blocks
# are therefore built as their own 40-trial units, each internally free of
# repeats. 40 x 3 = 120 concepts, comfortably inside the 229 available; the
# hard ceiling is 76 trials.
ADULT_BLOCK_N = 40
N_ADULT_BLOCKS = 10
ACTIVE_ADULT_BLOCKS = 10
TRAINING_N = 4
WARMUP_N = 4
CATCH_N = 3

PAIR_SPOSE_MIN = 0.70
MAX_CROSS_TRIAL_SIM = 0.88     # within a session only
KID_KNOWN_THRESHOLD = 0.95

BINS = [
    ("very hard", 0.40, 0.55),
    ("hard",      0.55, 0.70),
    ("medium",    0.70, 0.80),
    ("easy",      0.80, 0.90),
    ("very easy", 0.90, 0.95),
]
VIS_AGREE_MIN = 0.03
VIS_CONFLICT_MAX = -0.01
TRAINING_P_MIN = 0.97
WARMUP_P_MIN = 0.93

RNG = random.Random(20260813)


def load_all():
    clip = np.load(DERIVED / "clip_image_sim.npy")
    names = json.loads((DERIVED / "clip_concepts.json").read_text())
    cidx = {n: i for i, n in enumerate(names)}
    ids = (RAW / "unique_id.txt").read_text().splitlines()
    sidx = {u: i for i, u in enumerate(ids)}
    spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]
    emb = np.loadtxt(RAW / "spose_embedding_66d.txt")

    df = pd.read_csv(CONCEPTS_TSV, sep="\t")
    df["Percent_known"] = pd.to_numeric(df["Percent_known"], errors="coerce")
    c1, c2 = "Top-down Category (manual selection)", "Top-down Category (WordNet)"
    df["top_cat"] = df[c1].where(df[c1].notna() & (df[c1] != ""), df[c2])
    cat, known = {}, {}
    for _, r in df.iterrows():
        uid = str(r["uniqueID"])
        if uid not in cidx:
            continue
        t = r["top_cat"]
        if isinstance(t, str) and t.strip() and t.strip().lower() != "nan":
            cat[uid] = t.strip().lower().split(",")[0].strip()
        known[uid] = bool(r["Percent_known"] >= KID_KNOWN_THRESHOLD)
    return clip, cidx, spose, emb, sidx, cat, known, names


class Builder:
    def __init__(self):
        (self.clip, self.cidx, self.spose, self.emb,
         self.sidx, self.cat, self.known, self.names) = load_all()
        self.pool = [n for n in self.names if n in self.sidx and n in self.cat]
        self.pairs = []
        for i in range(len(self.pool)):
            for j in range(i + 1, len(self.pool)):
                a, b = self.pool[i], self.pool[j]
                if self.spose[self.sidx[a], self.sidx[b]] >= PAIR_SPOSE_MIN:
                    self.pairs.append((a, b))
        RNG.shuffle(self.pairs)
        print(f"{len(self.pool)} concepts, {len(self.pairs)} conceptually similar pairs")

    def s_vis(self, a, b):
        return float(self.clip[self.cidx[a], self.cidx[b]])

    def p_odd(self, a, b, c):
        e, s = self.emb, self.sidx
        sab, sac, sbc = (float(e[s[a]] @ e[s[b]]),
                         float(e[s[a]] @ e[s[c]]), float(e[s[b]] @ e[s[c]]))
        m = max(sab, sac, sbc)
        return math.exp(sab - m) / sum(math.exp(x - m) for x in (sab, sac, sbc))

    def vis_margin(self, a, b, c):
        return self.s_vis(a, b) - max(self.s_vis(a, c), self.s_vis(b, c))

    def compatible(self, cands, session):
        """No concept reused within a session, and nothing near-identical."""
        for c in cands:
            if c in session:
                return False
            if any(self.s_vis(c, prev) >= MAX_CROSS_TRIAL_SIM for prev in session):
                return False
        return True

    def make(self, tid, tier, cond, a, b, c, bin_lbl=None):
        triple, order = [a, b, c], [0, 1, 2]
        RNG.shuffle(order)
        shown = [triple[k] for k in order]
        t = {
            "trial_id": tid, "tier": tier, "dataset": "vocab_gradient_spose",
            "condition": cond, "n_objects": 3, "oddity_index": order.index(2),
            "images": [f"stimuli/{x}.jpg" for x in shown],
            "concepts": shown, "odd_concept": c, "pair_concepts": [a, b],
            "pair_category": self.cat.get(a), "odd_category": self.cat.get(c),
            "spose_sim_pair": round(float(self.spose[self.sidx[a], self.sidx[b]]), 3),
            "p_correct_spose": round(self.p_odd(a, b, c), 3),
            "vis_sim_pair": round(self.s_vis(a, b), 3),
            "vis_margin": round(self.vis_margin(a, b, c), 3),
            "human_avg_adult": None, "rt_avg_adult": None,
        }
        if bin_lbl:
            t["difficulty_bin"] = bin_lbl
        return t

    def find(self, session, cond, p_lo, p_hi, friendly_only=False):
        """One trial in the given condition and difficulty band that fits the
        session's no-repeat constraint. Conflict is searched first by the
        caller because it is the scarce condition."""
        v_lo, v_hi = ((VIS_AGREE_MIN, 9.0) if cond == "visual_agree"
                      else (-9.0, VIS_CONFLICT_MAX))
        pool = [n for n in self.pool if self.known.get(n)] if friendly_only else self.pool
        pool_set = set(pool)
        for a, b in self.pairs:
            if a not in pool_set or b not in pool_set:
                continue
            if not self.compatible([a, b], session):
                continue
            cands = pool[:]
            RNG.shuffle(cands)
            for c in cands:
                if c in (a, b) or not self.compatible([c], session | {a, b}):
                    continue
                if self.cat.get(c) in (self.cat.get(a), self.cat.get(b)):
                    continue
                p = self.p_odd(a, b, c)
                if not (p_lo <= p < p_hi):
                    continue
                vm = self.vis_margin(a, b, c)
                if not (v_lo <= vm < v_hi):
                    continue
                return a, b, c
        return None

    def build_set(self, prefix, n, session):
        """n trials balanced 50/50 across conditions and spread over the
        difficulty bins. Conflict allocated first — it is the scarce one."""
        out = []
        per_cond = n // 2
        plan = []
        for k in range(per_cond):
            plan.append(("visual_conflict", BINS[k % len(BINS)]))
        for k in range(n - per_cond):
            plan.append(("visual_agree", BINS[k % len(BINS)]))
        plan.sort(key=lambda x: x[0] != "visual_conflict")   # conflict first
        for i, (cond, (lbl, lo, hi)) in enumerate(plan):
            got = self.find(session, cond, lo, hi)
            if got is None:                     # widen the band if starved
                got = self.find(session, cond, 0.40, 0.95)
            if got is None:
                continue
            a, b, c = got
            out.append(self.make(f"{prefix}_{i:02d}", "familiar", cond, a, b, c, lbl))
            session |= {a, b, c}
        return out

    def build_intro(self, session):
        """Training, warmup, catch — nameable items, obvious answers."""
        intro = []
        for tier, count, floor in (("training", TRAINING_N, TRAINING_P_MIN),
                                   ("warmup", WARMUP_N, WARMUP_P_MIN)):
            for i in range(count):
                got = self.find(session, "visual_agree", floor, 1.01, friendly_only=True)
                if got is None:
                    break
                a, b, c = got
                intro.append(self.make(f"{tier}_{i:02d}", tier,
                                       f"{self.cat.get(a)}_vs_{self.cat.get(c)}", a, b, c))
                session |= {a, b, c}
        # Catch: same image twice plus a maximally distant one.
        friendly = [n for n in self.pool if self.known.get(n)]
        RNG.shuffle(friendly)
        made = 0
        for a in friendly:
            if made >= CATCH_N:
                break
            if not self.compatible([a], session):
                continue
            inv = {v: k for k, v in self.cidx.items()}
            c = next((inv[j] for j in np.argsort(self.clip[self.cidx[a]])
                      if inv[j] != a and self.compatible([inv[j]], session | {a})), None)
            if c is None:
                continue
            triple, order = [a, a, c], [0, 1, 2]
            RNG.shuffle(order)
            shown = [triple[k] for k in order]
            intro.append({
                "trial_id": f"catch_{made:02d}", "tier": "catch",
                "dataset": "vocab_gradient_spose", "condition": "attention_check",
                "n_objects": 3, "oddity_index": order.index(2),
                "images": [f"stimuli/{x}.jpg" for x in shown],
                "concepts": shown, "odd_concept": c, "pair_concepts": [a, a],
                "duplicate_image": True, "vis_sim_pair": 1.0,
                "human_avg_adult": None, "rt_avg_adult": None,
            })
            session |= {a, c}
            made += 1
        return intro


def main():
    b = Builder()

    # Core + intro share one session namespace: every child sees all of them.
    session = set()
    intro = b.build_intro(session)
    core = b.build_set("core", CORE_N, session)
    print(f"intro: {len(intro)} (training/warmup/catch)")
    print(f"core : {len(core)} "
          f"({sum(t['condition']=='visual_conflict' for t in core)} conflict / "
          f"{sum(t['condition']=='visual_agree' for t in core)} agree)")

    # Each block only has to avoid the core + intro concepts and its own.
    fixed = {c for t in intro + core for c in t["concepts"]}
    blocks = []
    for k in range(N_BLOCKS):
        blk = b.build_set(f"blk{k:02d}", BLOCK_N, set(fixed))
        blocks.append(blk)
    sizes = [len(x) for x in blocks]
    conf = [sum(t["condition"] == "visual_conflict" for t in x) for x in blocks]
    print(f"blocks: {len(blocks)} x {min(sizes)}-{max(sizes)} trials, "
          f"conflict per block {min(conf)}-{max(conf)}")

    # Adult blocks: same construction, twice the length, drawn fresh so each
    # is internally repeat-free rather than a concatenation of child blocks.
    adult_blocks = []
    for k in range(N_ADULT_BLOCKS):
        blk = b.build_set(f"adlt{k:02d}", ADULT_BLOCK_N, set(fixed))
        adult_blocks.append(blk)
    asizes = [len(x) for x in adult_blocks]
    aconf = [sum(t["condition"] == "visual_conflict" for t in x) for x in adult_blocks]
    print(f"adult blocks: {len(adult_blocks)} x {min(asizes)}-{max(asizes)} trials, "
          f"conflict per block {min(aconf)}-{max(aconf)}")

    all_trials = (intro + core + [t for blk in blocks for t in blk]
                  + [t for blk in adult_blocks for t in blk])
    concepts = sorted({c for t in all_trials for c in t["concepts"]})
    write_stimuli(concepts)

    n_rot = sum(sizes) + sum(asizes)
    manifest = {
        "meta": {
            "core_n": len(core), "block_n": BLOCK_N,
            "n_blocks": len(blocks), "active_blocks": ACTIVE_BLOCKS,
            "adult_block_n": ADULT_BLOCK_N,
            "n_adult_blocks": len(adult_blocks),
            "active_adult_blocks": ACTIVE_ADULT_BLOCKS,
            "session_length": len(intro) + len(core) + BLOCK_N,
            "adult_session_length": len(intro) + len(core) + ADULT_BLOCK_N,
            "bank_size": len(core) + n_rot,
            "distinct_concepts": len(concepts),
            "note": "Each child does intro + core + ONE block chosen at random "
                    "from the first `active_blocks`. No concept repeats within "
                    "a session.",
        },
        "intro": intro,
        "core": core,
        "blocks": blocks,
        "adult_blocks": adult_blocks,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1))
    print(f"\nbank: {len(core)+n_rot} trials, session = "
          f"{manifest['meta']['session_length']}, {len(concepts)} images")
    print(f"per rotating item at 200 usable children: "
          f"{200/ACTIVE_BLOCKS:.0f}")
    print(f"wrote {MANIFEST_PATH}")


def write_stimuli(concepts):
    if STIMULI_DIR.exists():
        shutil.rmtree(STIMULI_DIR)
    STIMULI_DIR.mkdir(parents=True)
    for c in concepts:
        im = Image.open(IMAGE_DIR / f"{c}.jpg").convert("RGB")
        im.thumbnail((JPEG_MAX_DIM, JPEG_MAX_DIM), Image.LANCZOS)
        im.save(STIMULI_DIR / f"{c}.jpg", quality=JPEG_QUALITY)
    print(f"wrote {len(concepts)} shared images -> {STIMULI_DIR}")


if __name__ == "__main__":
    main()

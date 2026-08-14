"""Emit the per-trial similarity terms behind each intended answer.

The deployed manifest stores only what the experiment needs at runtime
(pair similarity, predicted P, visual margin). Reviewing whether an answer
is defensible needs the full set — how close the odd item sits to *each*
pair member in both spaces. This recomputes those from the same matrices
the bank was built with and writes them alongside, so the live manifest is
never touched.

Output: analysis/stimulus_reasoning.csv, one row per trial.

Run:  python3 analysis/build_reasoning_table.py
"""

import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
DERIVED = ROOT / "rendering" / "_derived"
OUT = ROOT / "analysis" / "stimulus_reasoning.csv"

clip = np.load(DERIVED / "clip_image_sim.npy")
names = json.loads((DERIVED / "clip_concepts.json").read_text())
ci = {n: i for i, n in enumerate(names)}
ids = (RAW / "unique_id.txt").read_text().splitlines()
si = {u: i for i, u in enumerate(ids)}
spose = loadmat(RAW / "spose_similarity.mat")["spose_sim"]
emb = np.loadtxt(RAW / "spose_embedding_66d.txt")

man = json.loads((ROOT / "public" / "manifest.json").read_text())
trials = (man.get("intro", []) + man.get("core", [])
          + [t for b in man.get("blocks", []) for t in b])


def sc(a, b):
    return float(spose[si[a], si[b]]) if a in si and b in si else float("nan")


def vs(a, b):
    return float(clip[ci[a], ci[b]]) if a in ci and b in ci else float("nan")


def triplet_p(a, b, c):
    if not all(x in si for x in (a, b, c)):
        return float("nan")
    sab, sac, sbc = (float(emb[si[a]] @ emb[si[b]]),
                     float(emb[si[a]] @ emb[si[c]]), float(emb[si[b]] @ emb[si[c]]))
    m = max(sab, sac, sbc)
    return math.exp(sab - m) / sum(math.exp(x - m) for x in (sab, sac, sbc))


def which_block(tid):
    return int(tid[3:5]) if tid.startswith("blk") else ""


rows = []
for t in trials:
    tid = t["trial_id"]
    pair = t.get("pair_concepts") or []
    c = t.get("odd_concept")
    dup = bool(t.get("duplicate_image"))
    if len(pair) < 2 or not c:
        continue
    a, b = pair[0], pair[1]
    section = ("core" if tid.startswith("core")
               else "block" if tid.startswith("blk") else t.get("tier", ""))
    rows.append({
        "trial_id": tid, "section": section, "block": which_block(tid),
        "tier": t.get("tier"), "condition": t.get("condition"),
        "difficulty_bin": t.get("difficulty_bin", ""),
        "duplicate_image": int(dup),
        "img_1": t["concepts"][0], "img_2": t["concepts"][1], "img_3": t["concepts"][2],
        "oddity_index": t["oddity_index"],
        "odd_concept": c, "pair_a": a, "pair_b": b,
        "pair_category": t.get("pair_category", ""),
        "odd_category": t.get("odd_category", ""),
        # Conceptual space (the selector)
        "spose_pair": round(sc(a, b), 3),
        "spose_odd_a": round(sc(a, c), 3) if not dup else "",
        "spose_odd_b": round(sc(b, c), 3) if not dup else "",
        "p_correct_spose": round(triplet_p(a, b, c), 3) if not dup else "",
        # Visual space (the crossed factor)
        "clip_pair": round(vs(a, b), 3),
        "clip_odd_a": round(vs(a, c), 3),
        "clip_odd_b": round(vs(b, c), 3),
        "clip_margin": t.get("vis_margin", ""),
    })

with OUT.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"wrote {len(rows)} trials -> {OUT}")

"""Sample odd-one-out triplets spanning the full SPoSE difficulty gradient,
and render an HTML contact sheet so you can eyeball what each difficulty
level actually looks like.

`curate_things.py` deliberately keeps only very easy trials (all its
familiar-tier items sit between P = .94 and P = .996 — a ceiling, not a
gradient). This script instead samples across bins of predicted adult
accuracy, from near-chance to near-ceiling, so the item-difficulty range
is visible before committing to a trial set.

The "pair" (a, b) is still a same-category, high-similarity pair; what
varies is how semantically close the odd one out (c) is to that pair.

Outputs:
    rendering/gradient_preview.html   (open in a browser)
    rendering/gradient_preview.json   (the sampled trials)

Run:  python3 rendering/preview_gradient.py
"""

import json
import os
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
SPOSE_PATH = RAW / "spose_similarity.mat"
SPOSE_EMB_PATH = RAW / "spose_embedding_66d.txt"
UNIQUE_IDS_PATH = RAW / "unique_id.txt"

# Point at the *main* vocab-gradient checkout, not the _raw snapshot inside
# this repo. The two disagree (432 vs 467 images: the snapshot flattened in
# `_unused/` and is missing 85 items the paper used), and the constraint is
# 100% overlap with the published item set — so the paper's own checkout wins.
VG = Path("/Users/brialong/Documents/GitHub/vocab-gradient")
CONCEPTS_TSV = VG / "data" / "item_metadata" / "things_concepts.tsv"
IMAGE_DIR = VG / "stimuli" / "3_selected_stimuli" / "images_final2023-11-09"
TEST_ITEMS = VG / "data" / "item_metadata" / "test_items.csv"

OUT_HTML = ROOT / "rendering" / "gradient_preview.html"
OUT_JSON = ROOT / "rendering" / "gradient_preview.json"

KID_KNOWN_THRESHOLD = 0.95
PAIR_SIM_MIN = 0.70          # the two "go together" items must really go together
PER_BIN = 8
MAX_USES_PER_CONCEPT = 2

# Bins of SPoSE-predicted P(adult picks the intended odd one out).
BINS = [
    ("very hard",  0.40, 0.55),
    ("hard",       0.55, 0.70),
    ("medium",     0.70, 0.80),
    ("easy",       0.80, 0.90),
    ("very easy",  0.90, 0.95),
    ("ceiling",    0.95, 1.01),
]

RNG = random.Random(7)


def triplet_prob(emb, ia, ib, ic):
    """P(c chosen as odd | triplet) — softmax over pairwise SPoSE dot products."""
    sab = float(emb[ia] @ emb[ib])
    sac = float(emb[ia] @ emb[ic])
    sbc = float(emb[ib] @ emb[ic])
    m = max(sab, sac, sbc)
    z = math.exp(sab - m) + math.exp(sac - m) + math.exp(sbc - m)
    return math.exp(sab - m) / z


def paper_concepts():
    """The exact concept set used in the vocab-gradient paper: every target
    (Word1) and every distractor (Word2) in test_items.csv — 110 targets x
    (hard, easy, distal) distractors. Restricting to this guarantees 100%
    overlap with the published item set, so oddity performance can be joined
    against the paper's existing item-level 4AFC data."""
    ti = pd.read_csv(TEST_ITEMS)
    return set(ti["Word1"].dropna()) | set(ti["Word2"].dropna())


def load_concepts(ids_list, available):
    paper = paper_concepts()
    df = pd.read_csv(CONCEPTS_TSV, sep="\t")
    df = df[df["uniqueID"].astype(str).isin(paper)]
    df["Percent_known"] = pd.to_numeric(df["Percent_known"], errors="coerce")
    cat_col = "Top-down Category (manual selection)"
    wn_col = "Top-down Category (WordNet)"
    df["top_cat"] = df[cat_col].where(df[cat_col].notna() & (df[cat_col] != ""), df[wn_col])

    in_matrix = {uid: i for i, uid in enumerate(ids_list)}
    keep = {}
    for _, row in df.iterrows():
        uid = str(row["uniqueID"])
        if uid not in available or uid not in in_matrix:
            continue
        if not (row["Percent_known"] >= KID_KNOWN_THRESHOLD):
            continue
        top = row.get("top_cat")
        if top is None or (isinstance(top, float) and math.isnan(top)):
            continue
        top = str(top).strip().lower().split(",")[0].strip()
        if not top or top == "nan":
            continue
        keep[uid] = {"idx": in_matrix[uid], "cat": top, "img": available[uid]}
    return keep


def main():
    emb = np.loadtxt(SPOSE_EMB_PATH)
    sim = loadmat(SPOSE_PATH)["spose_sim"]
    ids_list = UNIQUE_IDS_PATH.read_text().splitlines()
    available = {p.stem: p for p in IMAGE_DIR.glob("*.jpg")}
    concepts = load_concepts(ids_list, available)
    names = sorted(concepts)
    print(f"{len(concepts)} kid-known concepts with images and SPoSE entries")

    # Same-category high-similarity pairs.
    by_cat = {}
    for n in names:
        by_cat.setdefault(concepts[n]["cat"], []).append(n)
    pairs = []
    for cat, members in by_cat.items():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                s = float(sim[concepts[a]["idx"], concepts[b]["idx"]])
                if s >= PAIR_SIM_MIN:
                    pairs.append((a, b, s, cat))
    RNG.shuffle(pairs)
    print(f"{len(pairs)} same-category pairs above sim {PAIR_SIM_MIN}")

    # For every pair, score every candidate third item and bin by difficulty.
    bins = {label: [] for label, _, _ in BINS}
    uses = {}

    def can_use(*cs):
        return all(uses.get(c, 0) < MAX_USES_PER_CONCEPT for c in cs)

    for a, b, pair_sim, cat in pairs:
        if all(len(bins[l]) >= PER_BIN for l, _, _ in BINS):
            break
        if not can_use(a, b):
            continue
        ia, ib = concepts[a]["idx"], concepts[b]["idx"]
        cands = [c for c in names if c not in (a, b)]
        RNG.shuffle(cands)
        for c in cands:
            ic = concepts[c]["idx"]
            p = triplet_prob(emb, ia, ib, ic)
            for label, lo, hi in BINS:
                if lo <= p < hi and len(bins[label]) < PER_BIN and can_use(a, b, c):
                    bins[label].append({
                        "bin": label,
                        "concepts": [a, b, c],
                        "odd": c,
                        "pair_category": cat,
                        "odd_category": concepts[c]["cat"],
                        "pair_sim": round(pair_sim, 3),
                        "sim_odd_to_a": round(float(sim[ia, ic]), 3),
                        "sim_odd_to_b": round(float(sim[ib, ic]), 3),
                        "p_correct_spose": round(p, 3),
                        # Relative to rendering/, so the HTML resolves images
                        # in whichever checkout IMAGE_DIR points at.
                        "images": [os.path.relpath(concepts[x]["img"], ROOT / "rendering")
                                   for x in (a, b, c)],
                    })
                    for x in (a, b, c):
                        uses[x] = uses.get(x, 0) + 1
                    break
            else:
                continue
            break

    trials = [t for label, _, _ in BINS for t in
              sorted(bins[label], key=lambda z: z["p_correct_spose"])]
    for label, _, _ in BINS:
        print(f"  {label:<10} {len(bins[label])} trials")

    OUT_JSON.write_text(json.dumps(trials, indent=2))
    OUT_HTML.write_text(render_html(bins))
    print(f"\nwrote {OUT_JSON}\nwrote {OUT_HTML}")


def render_html(bins):
    css = """
    :root { color-scheme: light dark; }
    body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 32px;
           background: #fafafa; color: #1a1a1a; }
    @media (prefers-color-scheme: dark) { body { background: #16181c; color: #e8e8ea; } }
    h1 { font-size: 22px; margin: 0 0 6px; }
    .sub { opacity: .7; font-size: 14px; margin-bottom: 28px; max-width: 70ch; line-height: 1.5; }
    h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .07em; opacity: .65;
         margin: 34px 0 14px; padding-bottom: 6px; border-bottom: 1px solid rgba(128,128,128,.3); }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }
    .trial { background: rgba(128,128,128,.08); border-radius: 12px; padding: 12px; }
    .imgs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .imgs figure { margin: 0; }
    .imgs img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px;
                display: block; background: rgba(128,128,128,.15); }
    .imgs figcaption { font-size: 11px; text-align: center; margin-top: 4px; opacity: .75; }
    .odd img { outline: 3px solid #e8873a; outline-offset: 1px; }
    .odd figcaption { color: #e8873a; font-weight: 600; opacity: 1; }
    .meta { font-size: 11px; opacity: .7; margin-top: 9px; line-height: 1.45;
            font-variant-numeric: tabular-nums; }
    .p { font-weight: 700; font-size: 13px; opacity: 1; }
    """
    parts = [f"<title>THINGS oddity — difficulty gradient</title><style>{css}</style>",
             "<h1>Odd-one-out trials across the SPoSE difficulty gradient</h1>",
             "<div class='sub'>Each trial: two same-category concepts that go together, plus one odd "
             "item (orange outline). <b>P</b> is the SPoSE-predicted probability an adult picks the "
             "intended odd item; chance is .33. The current <code>curate_things.py</code> set lives "
             "entirely in the bottom two bins — everything above is what a graded set would add.</div>"]
    for label, lo, hi in BINS:
        items = sorted(bins[label], key=lambda z: z["p_correct_spose"])
        if not items:
            continue
        parts.append(f"<h2>{label} &nbsp;·&nbsp; P = {lo:.2f}–{min(hi,1.0):.2f} &nbsp;·&nbsp; {len(items)} trials</h2>")
        parts.append("<div class='grid'>")
        for t in items:
            figs = "".join(
                f"<figure class='{'odd' if name == t['odd'] else ''}'>"
                f"<img src='{img}' alt='{name}' loading='lazy'>"
                f"<figcaption>{name}</figcaption></figure>"
                for name, img in zip(t["concepts"], t["images"]))
            parts.append(
                f"<div class='trial'><div class='imgs'>{figs}</div>"
                f"<div class='meta'><span class='p'>P = {t['p_correct_spose']:.2f}</span> &nbsp; "
                f"pair sim {t['pair_sim']:.2f} &nbsp; odd sim {t['sim_odd_to_a']:.2f}/{t['sim_odd_to_b']:.2f}<br>"
                f"{t['pair_category']} + {t['odd_category']}</div></div>")
        parts.append("</div>")
    return "\n".join(parts)


if __name__ == "__main__":
    main()

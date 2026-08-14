"""Curate the THINGS Kids semantic-outlier oddity trial set.

For each triplet of THINGS concepts (a, b, c), we want adults to reliably
pick c as the odd one out: i.e., s(a, b) should be large and s(a, c),
s(b, c) should be small. Under the SPoSE model (Hebart et al. 2023), a
rough predictor of P(adults pick c as odd) is

    s(a, b) / (s(a, b) + s(a, c) + s(b, c))

where `s` is the modelled pairwise concept similarity (spose_similarity.mat,
1854 x 1854, in [0, 1]).

Strategy:
- Restrict to concepts that (i) have an image in vocab-gradient's
  3_selected_stimuli/images_final2023-11-09/, (ii) have Percent_known >=
  0.95 (well-known to children), (iii) have a non-empty Top-down Category.
- Within each top-down category, take all in-category pairs with high
  similarity. For each pair, find an out-of-category third concept that's
  far from both. Compute the SPoSE-predicted adult accuracy; keep triplets
  above a tier-specific threshold.
- Sample tiers: 12 training (P > 0.99, very obvious), 12 warmup
  (P > 0.95), 56 familiar (P > 0.85), and 6 catch (same image x2 plus a
  category-mismatch image — pure attention check).

Outputs (overwrites):
    public/stimuli/<trial_id>/{0,1,2}.jpg
    public/manifest.json

Inputs:
    rendering/_raw/spose_similarity.mat
    rendering/_raw/unique_id.txt
    rendering/_raw/vocab-gradient/data/item_metadata/things_concepts.tsv
    rendering/_raw/vocab-gradient/stimuli/3_selected_stimuli/images_final2023-11-09/
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

random.seed(42)
RNG = random.Random(42)

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "rendering" / "_raw"
SPOSE_PATH = RAW / "spose_similarity.mat"           # 1854x1854 pairwise sim (kept for sanity)
SPOSE_EMB_PATH = RAW / "spose_embedding_66d.txt"   # 1854x66 SPoSE embedding
UNIQUE_IDS_PATH = RAW / "unique_id.txt"
CONCEPTS_TSV = RAW / "vocab-gradient" / "data" / "item_metadata" / "things_concepts.tsv"
IMAGE_DIR = RAW / "vocab-gradient" / "stimuli" / "3_selected_stimuli" / "images_final2023-11-09"

STIMULI_DIR = ROOT / "public" / "stimuli"
MANIFEST_PATH = ROOT / "public" / "manifest.json"

# Tier composition (matches mochi-kids; "novel" is omitted because these
# are all real, familiar objects — no abstract-shape tier exists here).
TRAINING_N = 12
WARMUP_N = 12
FAMILIAR_N = 56
CATCH_N = 6

# SPoSE-predicted-adult-accuracy thresholds per tier.
THRESH_TRAINING = 0.99
THRESH_WARMUP = 0.95
THRESH_FAMILIAR = 0.85

# Kid-friendliness: a concept is "known" if >= 95% of kids in the THINGS
# norms could identify it.
KID_KNOWN_THRESHOLD = 0.95

# Within-category pair similarity floor (the two "same-category" items
# should be substantively similar). Otherwise random pairs of e.g. "fork"
# and "freezer" qualify and the trial isn't truly category-based.
PAIR_SIM_MIN = 0.70

# Outlier similarity ceiling: the third concept's avg similarity to the
# pair must be at most this.
OUTLIER_SIM_MAX = 0.45

JPEG_MAX_DIM = 512
JPEG_QUALITY = 88


# ============ data loading ============

def load_similarity():
    """Load both the 66-D SPoSE embedding (for proper triplet probabilities
    via softmax over pairwise dot products) and the derived pairwise
    similarity matrix (for the within-category pair floor — a more
    bounded, intuitive metric)."""
    print("loading SPoSE embedding + similarity matrix…")
    emb = np.loadtxt(SPOSE_EMB_PATH)
    sim = loadmat(SPOSE_PATH)["spose_sim"]
    ids = UNIQUE_IDS_PATH.read_text().splitlines()
    assert emb.shape == (1854, 66), emb.shape
    assert sim.shape == (1854, 1854), sim.shape
    return emb, sim, ids


def triplet_prob(emb, ia, ib, ic):
    """Softmax over pairwise dot products under SPoSE.
    Returns P(c chosen as odd | triplet a, b, c)."""
    sab = float(emb[ia] @ emb[ib])
    sac = float(emb[ia] @ emb[ic])
    sbc = float(emb[ib] @ emb[ic])
    # Subtract max for numeric stability.
    m = max(sab, sac, sbc)
    z = math.exp(sab - m) + math.exp(sac - m) + math.exp(sbc - m)
    return math.exp(sab - m) / z


def load_concepts():
    print("loading THINGS concept metadata…")
    df = pd.read_csv(CONCEPTS_TSV, sep="\t")
    df["Percent_known"] = pd.to_numeric(df["Percent_known"], errors="coerce")
    # Prefer manual top-down category, fall back to WordNet's.
    cat_col = "Top-down Category (manual selection)"
    wn_col = "Top-down Category (WordNet)"
    df["top_cat"] = df[cat_col].where(df[cat_col].notna() & (df[cat_col] != ""), df[wn_col])
    return df


def list_available_concepts():
    """Concepts that have a 300x300 image in vocab-gradient. Image filenames
    are lowercase concept names (no spaces — multi-word concepts use the
    THINGS uniqueID convention with underscores)."""
    files = list(IMAGE_DIR.glob("*.jpg"))
    return {p.stem: p for p in files}


# ============ candidate filtering ============

def kid_friendly_concepts(concepts_df, available, ids_list):
    """Concepts that (i) have an image in vocab-gradient, (ii) are well-known
    to children, (iii) appear in the SPoSE matrix, (iv) have a usable top-
    down category. Returns dict name -> {idx, cat, img}."""
    in_matrix = set(ids_list)
    keep = {}
    for _, row in concepts_df.iterrows():
        uid = str(row["uniqueID"])
        if uid not in available:
            continue
        if uid not in in_matrix:
            continue
        if not (row["Percent_known"] >= KID_KNOWN_THRESHOLD):
            continue
        top = row.get("top_cat")
        if top is None or (isinstance(top, float) and math.isnan(top)):
            continue
        top = str(top).strip().lower()
        if not top or top == "nan":
            continue
        # Normalise multi-label categories like "food, fruit" -> "food".
        top = top.split(",")[0].strip()
        keep[uid] = {
            "idx": ids_list.index(uid),
            "cat": top,
            "img": available[uid],
        }
    return keep


# ============ triplet scoring ============

def find_triplet(emb, sim, concepts, pair, threshold, rng):
    """Given a same-category pair (a, b), find a 3rd concept (different
    top-down category) where the SPoSE softmax probability of picking c
    as odd is at or above `threshold`. Returns (third_name, prob) or None.

    Uses two cues:
      1. spose_sim[a, c] + spose_sim[b, c]  must each be <= OUTLIER_SIM_MAX
         (cheap pre-filter against semantically near-by 3rds).
      2. triplet_prob via softmax over 66-D embedding dot products is the
         actual ranking metric.
    """
    a, b = pair
    ia = concepts[a]["idx"]; ib = concepts[b]["idx"]
    cat_a = concepts[a]["cat"]; cat_b = concepts[b]["cat"]

    candidates = [name for name, info in concepts.items()
                  if info["cat"] not in {cat_a, cat_b}
                  and name not in {a, b}]
    rng.shuffle(candidates)

    best = None
    best_p = -1.0
    for c in candidates:
        ic = concepts[c]["idx"]
        if sim[ia, ic] > OUTLIER_SIM_MAX or sim[ib, ic] > OUTLIER_SIM_MAX:
            continue
        p = triplet_prob(emb, ia, ib, ic)
        if p > best_p:
            best_p = p; best = c
        if p >= threshold + 0.02:
            return c, p
    if best_p >= threshold:
        return best, best_p
    return None


def enumerate_pairs(sim, concepts, used_concepts=None):
    """Same-category pairs above the within-cat similarity floor. Returns
    list of (a, b, similarity) sorted by similarity desc."""
    by_cat = {}
    for name, info in concepts.items():
        if used_concepts and name in used_concepts:
            continue
        by_cat.setdefault(info["cat"], []).append(name)
    pairs = []
    for cat, names in by_cat.items():
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                s = sim[concepts[a]["idx"], concepts[b]["idx"]]
                if s >= PAIR_SIM_MIN:
                    pairs.append((a, b, s, cat))
    pairs.sort(key=lambda x: -x[2])
    return pairs


# ============ image writing ============

def write_image(src_path: Path, dest: Path):
    im = Image.open(src_path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((JPEG_MAX_DIM, JPEG_MAX_DIM), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)


def emit_trial(concepts, a, b, c, tier, trial_id, manifest, predicted_acc):
    """Write the 3 images and append the manifest entry. The two
    same-category images go to display indices 0 and 1; the outlier to 2."""
    folder = STIMULI_DIR / trial_id
    folder.mkdir(parents=True, exist_ok=True)
    write_image(concepts[a]["img"], folder / "0.jpg")
    write_image(concepts[b]["img"], folder / "1.jpg")
    write_image(concepts[c]["img"], folder / "2.jpg")
    manifest.append({
        "trial_id": trial_id,
        "tier": tier,
        "dataset": "things",
        "condition": f"{concepts[a]['cat']}_vs_{concepts[c]['cat']}",
        "n_objects": 3,
        "oddity_index": 2,
        "images": [
            f"stimuli/{trial_id}/0.jpg",
            f"stimuli/{trial_id}/1.jpg",
            f"stimuli/{trial_id}/2.jpg",
        ],
        "concepts": [a, b, c],
        "human_avg_adult": float(predicted_acc),
        "rt_avg_adult": None,
    })


# ============ catch trials ============

def synthesize_catch(concepts, n, manifest):
    """Same image x2 + 1 obviously-different image. Pop-out attention
    checks — every kid should get them right."""
    names = list(concepts.keys())
    RNG.shuffle(names)
    used = set()
    made = 0
    for same in names:
        if made >= n:
            break
        if same in used:
            continue
        # Pick a different-category image with low similarity (any will do
        # — these are visual pop-outs of identical pairs).
        sim_to_same = None  # not used; just want any cross-category target
        cat_same = concepts[same]["cat"]
        diffs = [m for m in names
                 if m != same and m not in used and concepts[m]["cat"] != cat_same]
        if not diffs:
            continue
        diff = diffs[0]
        trial_id = f"catch_{made:02d}"
        folder = STIMULI_DIR / trial_id
        folder.mkdir(parents=True, exist_ok=True)
        write_image(concepts[same]["img"], folder / "0.jpg")
        write_image(concepts[same]["img"], folder / "1.jpg")
        write_image(concepts[diff]["img"], folder / "2.jpg")
        manifest.append({
            "trial_id": trial_id,
            "tier": "catch",
            "dataset": "catch",
            "condition": f"{cat_same}_identity_vs_{concepts[diff]['cat']}",
            "n_objects": 3,
            "oddity_index": 2,
            "images": [
                f"stimuli/{trial_id}/0.jpg",
                f"stimuli/{trial_id}/1.jpg",
                f"stimuli/{trial_id}/2.jpg",
            ],
            "concepts": [same, same, diff],
            "human_avg_adult": 1.0,
            "rt_avg_adult": None,
        })
        used.add(same); used.add(diff)
        made += 1


# ============ main ============

def main():
    emb, sim, ids = load_similarity()
    df_concepts = load_concepts()
    available = list_available_concepts()
    print(f"vocab-gradient images: {len(available)}")

    concepts = kid_friendly_concepts(df_concepts, available, ids)
    print(f"kid-friendly concepts after filters: {len(concepts)}")
    # Show category breakdown.
    cats = {}
    for info in concepts.values():
        cats[info["cat"]] = cats.get(info["cat"], 0) + 1
    print("  by category:", dict(sorted(cats.items(), key=lambda x: -x[1])[:10]), "…")

    # Wipe existing stimuli (preserve README if any).
    if STIMULI_DIR.exists():
        for child in STIMULI_DIR.iterdir():
            if child.name == "README.md":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    STIMULI_DIR.mkdir(parents=True, exist_ok=True)

    pairs = enumerate_pairs(sim, concepts)
    print(f"in-category pairs above sim {PAIR_SIM_MIN}: {len(pairs)}")

    manifest = []

    # Each tier tracks its own concept-uniqueness set so within-tier we get
    # variety; concepts can recur across tiers (the kid sees the same image
    # in different triplets, which is fine and standard in oddity tasks).
    # Pair-uniqueness is global so we never repeat the exact (a, b) pair.
    used_pairs = set()

    def build_tier(name, n, threshold, rng_seed):
        rng = random.Random(rng_seed)
        used_concepts = set()
        accs = []
        made = 0
        for a, b, _, _ in pairs:
            if made >= n:
                break
            if (a, b) in used_pairs:
                continue
            if a in used_concepts or b in used_concepts:
                continue
            found = find_triplet(emb, sim, concepts, (a, b), threshold, rng)
            if not found:
                continue
            c, acc = found
            if c in used_concepts:
                continue
            trial_id = f"{name}_{made:02d}"
            emit_trial(concepts, a, b, c, name, trial_id, manifest, acc)
            used_pairs.add((a, b))
            used_concepts.update([a, b, c])
            accs.append(acc)
            made += 1
        return made, accs

    print("building training triplets (P_adult >= "
          f"{THRESH_TRAINING})…")
    n_train, _ = build_tier("training", TRAINING_N, THRESH_TRAINING, 11)
    print(f"  training: {n_train}/{TRAINING_N} trials")

    print(f"building warmup triplets (P_adult >= {THRESH_WARMUP})…")
    n_warm, _ = build_tier("warmup", WARMUP_N, THRESH_WARMUP, 22)
    print(f"  warmup: {n_warm}/{WARMUP_N} trials")

    print(f"building familiar triplets (P_adult >= {THRESH_FAMILIAR})…")
    n_fam, fam_accs = build_tier("familiar", FAMILIAR_N, THRESH_FAMILIAR, 33)
    print(f"  familiar: {n_fam}/{FAMILIAR_N} trials, predicted-acc range "
          f"{min(fam_accs):.2f}-{max(fam_accs):.2f}, mean "
          f"{sum(fam_accs)/len(fam_accs):.2f}")

    # ----- catch: identity-match pop-outs -----
    print("building catch trials…")
    synthesize_catch(concepts, CATCH_N, manifest)

    # ----- shuffle within tiers, write manifest -----
    by_tier = {"training": [], "warmup": [], "familiar": [], "catch": []}
    for t in manifest:
        by_tier[t["tier"]].append(t)
    rng2 = random.Random(99)
    for k in ["familiar"]:
        rng2.shuffle(by_tier[k])
    final = (by_tier["training"] + by_tier["warmup"]
             + by_tier["familiar"] + by_tier["catch"])

    MANIFEST_PATH.write_text(json.dumps({"trials": final}, indent=2))
    counts = {k: len(v) for k, v in by_tier.items()}
    print(f"\nwrote {MANIFEST_PATH}")
    print(f"manifest: {counts}, total={sum(counts.values())}")


if __name__ == "__main__":
    main()

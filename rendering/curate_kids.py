"""Re-curate the MOCHI Kids trial set from the MOCHI parquet.

Strategy: per-category, sort by adult accuracy desc (then RT_avg asc) and
take the easiest N trials. Preserves human_avg + RT_avg in the manifest so
we can do real calibration analyses going forward.

Run from repo root:
    python3 rendering/curate_kids.py

Inputs:
    rendering/MOCHI/data/train-00000-of-00001.parquet

Outputs (overwrites):
    public/stimuli/<trial_id>/{0,1,2}.jpg
    public/manifest.json
"""

import io
import json
import random
import shutil
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

random.seed(42)  # reproducible

ROOT = Path(__file__).resolve().parent.parent
PARQUET = ROOT / "rendering" / "MOCHI" / "data" / "train-00000-of-00001.parquet"
STIMULI_DIR = ROOT / "public" / "stimuli"
MANIFEST_PATH = ROOT / "public" / "manifest.json"

# Tier composition.
WARMUP_CATEGORIES = ["chair", "lamp", "bench"]
FAMILIAR_CATEGORIES = ["chair", "lamp", "bench", "telephone",
                       "car", "airplane", "sofa", "table"]
# 8 cats × ~3.5 each = 28. First 4 cats get 4 trials, next 4 get 3.
FAMILIAR_PER_CAT_HIGH = 4   # chair, lamp, bench, telephone
FAMILIAR_PER_CAT_LOW = 3    # car, airplane, sofa, table
WARMUP_N = 12
# Novel: mix abstract4/3/2 to add a difficulty ramp instead of all-easy.
NOVEL_BREAKDOWN = {"abstract4": 12, "abstract3": 8, "abstract2": 8}  # 28 total
TRAINING_N = 12
# Catch trials: synthesized identity matches (same image x2 + 1 clearly
# different category image). Spliced into test blocks at runtime as
# attention checks — every kid should get them right.
CATCH_N = 6

JPEG_MAX_DIM = 512
JPEG_QUALITY = 88


def load_parquet():
    return pq.read_table(PARQUET).to_pandas()


def write_image(img_struct, dest: Path):
    """img_struct is {"bytes": ..., "path": ...} from MOCHI parquet."""
    im = Image.open(io.BytesIO(img_struct["bytes"]))
    if im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((JPEG_MAX_DIM, JPEG_MAX_DIM), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True)


# ============ object-in-frame filter ============
# A subset of MOCHI renders has the object cropped against the image edge.
# Kids learn a "tap whichever one's clipped" rule and stop comparing shapes,
# so we drop any trial whose images have non-white pixels on the border.
EDGE_THRESHOLD = 240   # >= this on every channel == effectively white
EDGE_NOISE_TOL = 1     # tolerate up to this many edge pixels darker than threshold


def _object_in_frame(img_struct) -> bool:
    """True if all four image borders are essentially white (object stays
    inside the frame). Tolerates a tiny amount of JPEG noise."""
    im = Image.open(io.BytesIO(img_struct["bytes"])).convert("RGB")
    w, h = im.size
    px = im.load()
    bad = 0
    for x in range(w):
        for y in (0, h - 1):
            r, g, b = px[x, y]
            if min(r, g, b) < EDGE_THRESHOLD:
                bad += 1
                if bad > EDGE_NOISE_TOL:
                    return False
    for y in range(h):
        for x in (0, w - 1):
            r, g, b = px[x, y]
            if min(r, g, b) < EDGE_THRESHOLD:
                bad += 1
                if bad > EDGE_NOISE_TOL:
                    return False
    return True


def _trial_in_frame(row) -> bool:
    return all(_object_in_frame(img) for img in row["images"])


def filter_in_frame(df_rows):
    """Filter a DataFrame of trials, dropping any whose images have an
    object touching the frame edge. Prints how many were dropped."""
    if len(df_rows) == 0:
        return df_rows
    keep_mask = df_rows.apply(_trial_in_frame, axis=1)
    n_drop = (~keep_mask).sum()
    if n_drop:
        print(f"    border filter: dropped {n_drop}/{len(df_rows)} trials with edge-clipped objects")
    return df_rows[keep_mask]


def take_easiest(rows, n):
    """Sort by human_avg desc, RT_avg asc; take top n."""
    return rows.sort_values(["human_avg", "RT_avg"],
                            ascending=[False, True]).head(n)


def take_random(rows, n, rng):
    """Reproducibly sample n rows from the bin (preserves natural difficulty
    distribution instead of clipping to ceiling)."""
    rows_sorted = rows.sort_values("trial").reset_index(drop=True)
    if len(rows_sorted) <= n:
        return rows_sorted
    idx = sorted(rng.sample(range(len(rows_sorted)), n))
    return rows_sorted.iloc[idx]


def emit_trial(row, tier, trial_id, manifest):
    """Write the 3 images for a row and append a manifest entry."""
    folder = STIMULI_DIR / trial_id
    images = []
    for i, img in enumerate(row["images"]):
        rel = f"stimuli/{trial_id}/{i}.jpg"
        write_image(img, ROOT / "public" / rel)
        images.append(rel)
    manifest.append({
        "trial_id": trial_id,
        "tier": tier,
        "dataset": str(row["dataset"]),
        "condition": str(row["condition"]),
        "n_objects": int(row["n_objects"]),
        "oddity_index": int(row["oddity_index"]),
        "images": images,
        "human_avg_adult": float(row["human_avg"]),
        "rt_avg_adult": float(row["RT_avg"]),
    })


def _synthesize_popouts(df, pairs, tier, id_prefix, manifest):
    """Shared helper: build pop-out trials from cross-category image pairs.
    Used for both training tier (start of session) and catch tier (sprinkled
    through the test blocks as attention checks)."""

    easy_by_cat = {}
    for cat in {c for pair in pairs for c in pair}:
        rows = df[(df["dataset"] == "shapenet") & (df["condition"] == cat)]
        easy_by_cat[cat] = rows.sort_values("human_avg", ascending=False).head(20)

    for i, (same_cat, diff_cat) in enumerate(pairs):
        same_row = easy_by_cat[same_cat].iloc[i % len(easy_by_cat[same_cat])]
        diff_row = easy_by_cat[diff_cat].iloc[i % len(easy_by_cat[diff_cat])]
        same_img = same_row["images"][0]
        diff_img = diff_row["images"][0]
        trial_id = f"{id_prefix}_{i:02d}"
        folder = STIMULI_DIR / trial_id
        folder.mkdir(parents=True, exist_ok=True)
        write_image(same_img, folder / "0.jpg")
        write_image(same_img, folder / "1.jpg")
        write_image(diff_img, folder / "2.jpg")
        manifest.append({
            "trial_id": trial_id,
            "tier": tier,
            "dataset": tier,
            "condition": f"{same_cat}_vs_{diff_cat}",
            "n_objects": 3,
            "oddity_index": 2,
            "images": [
                f"stimuli/{trial_id}/0.jpg",
                f"stimuli/{trial_id}/1.jpg",
                f"stimuli/{trial_id}/2.jpg",
            ],
            "human_avg_adult": 1.0,
            "rt_avg_adult": None,
        })


def synthesize_training(df, n, manifest):
    pairs = [
        ("chair", "telephone"), ("lamp", "bench"), ("bench", "telephone"),
        ("chair", "lamp"), ("airplane", "chair"), ("car", "lamp"),
        ("telephone", "bench"), ("lamp", "telephone"), ("bench", "chair"),
        ("airplane", "telephone"), ("car", "bench"), ("chair", "airplane"),
    ][:n]
    _synthesize_popouts(df, pairs, "training", "training", manifest)


def synthesize_catch(df, n, manifest):
    """Identity-match attention checks. Different category pairs from
    training so the kid hasn't seen the exact same image earlier."""
    pairs = [
        ("sofa", "lamp"), ("table", "telephone"), ("car", "chair"),
        ("airplane", "lamp"), ("telephone", "car"), ("bench", "airplane"),
        ("lamp", "car"), ("chair", "sofa"),
    ][:n]
    _synthesize_popouts(df, pairs, "catch", "catch", manifest)


def main():
    print("loading parquet…")
    df = load_parquet()

    # Wipe existing stimuli (except the README).
    if STIMULI_DIR.exists():
        for child in STIMULI_DIR.iterdir():
            if child.name == "README.md":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    STIMULI_DIR.mkdir(parents=True, exist_ok=True)

    manifest = []

    # 1. Training (synthesized pop-out at start of session).
    print(f"synthesizing {TRAINING_N} training trials…")
    synthesize_training(df, TRAINING_N, manifest)

    # 1b. Catch trials (synthesized pop-outs spliced into test blocks at runtime).
    print(f"synthesizing {CATCH_N} catch trials…")
    synthesize_catch(df, CATCH_N, manifest)

    # 2. Warmup: easiest trials from chair/lamp/bench (in-frame only).
    warmup_rows = df[(df["dataset"] == "shapenet")
                     & (df["n_objects"] == 3)
                     & (df["condition"].isin(WARMUP_CATEGORIES))]
    warmup_rows = filter_in_frame(warmup_rows)
    warmup_picks = take_easiest(warmup_rows, WARMUP_N)
    print(f"warmup: {len(warmup_picks)} picks (mean acc={warmup_picks['human_avg'].mean():.2f})")
    used_trial_ids = set(warmup_picks["trial"].tolist())
    for _, row in warmup_picks.iterrows():
        emit_trial(row, "warmup", str(row["trial"]), manifest)

    # 3. Familiar: top N easiest per category (excluding warmup picks).
    print(f"familiar: {len(FAMILIAR_CATEGORIES)} cats…")
    fam_total_acc = []
    for cat in FAMILIAR_CATEGORIES:
        per_cat = FAMILIAR_PER_CAT_HIGH if cat in {"chair", "lamp", "bench", "telephone"} else FAMILIAR_PER_CAT_LOW
        cat_rows = df[(df["dataset"] == "shapenet")
                      & (df["n_objects"] == 3)
                      & (df["condition"] == cat)
                      & (~df["trial"].isin(used_trial_ids))]
        cat_rows = filter_in_frame(cat_rows)
        picks = take_easiest(cat_rows, per_cat)
        print(f"  {cat}: {len(picks)}/{per_cat} (mean acc={picks['human_avg'].mean():.2f}, range {picks['human_avg'].min():.2f}-{picks['human_avg'].max():.2f})")
        fam_total_acc.extend(picks["human_avg"].tolist())
        for _, row in picks.iterrows():
            used_trial_ids.add(row["trial"])
            emit_trial(row, "familiar", str(row["trial"]), manifest)
    print(f"familiar overall mean acc: {sum(fam_total_acc)/len(fam_total_acc):.2f}")

    # 4. Novel: random sample from each abstract bin so we get the bin's
    # natural difficulty (not just ceiling). abstract4 mean=0.94, abstract3
    # mean=0.88, abstract2 mean=0.84 → mixed novel block lands around 0.89.
    print(f"novel: random sample from {NOVEL_BREAKDOWN}")
    novel_rng = random.Random(7)
    nov_total_acc = []
    for cond, n in NOVEL_BREAKDOWN.items():
        rows = df[(df["dataset"] == "shapegen")
                  & (df["n_objects"] == 3)
                  & (df["condition"] == cond)]
        rows = filter_in_frame(rows)
        picks = take_random(rows, n, novel_rng)
        print(f"  {cond}: {len(picks)} (mean acc={picks['human_avg'].mean():.2f}, range {picks['human_avg'].min():.2f}-{picks['human_avg'].max():.2f})")
        nov_total_acc.extend(picks["human_avg"].tolist())
        for _, row in picks.iterrows():
            emit_trial(row, "novel", str(row["trial"]), manifest)
    print(f"novel overall mean acc: {sum(nov_total_acc)/len(nov_total_acc):.2f}")

    # Keep each tier as its own block (internal shuffle only). The client
    # groups by tier at runtime, plays training -> warmup -> {familiar,
    # novel} in counterbalanced order, and splices catch trials throughout
    # the test phase as attention checks.
    by_tier = {"training": [], "warmup": [], "familiar": [],
               "novel": [], "catch": []}
    for t in manifest:
        by_tier[t["tier"]].append(t)
    rng = random.Random(42)
    for k in ["familiar", "novel"]:
        rng.shuffle(by_tier[k])
    final = (by_tier["training"] + by_tier["warmup"]
             + by_tier["familiar"] + by_tier["novel"] + by_tier["catch"])

    out = {"trials": final}
    MANIFEST_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {MANIFEST_PATH} with {len(final)} trials")
    print({tier: len(by_tier[tier]) for tier in by_tier})


if __name__ == "__main__":
    main()

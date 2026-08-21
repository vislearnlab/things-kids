"""Build basic-level oddity trials: two exemplars of one concept, one of another.

Two dogs and a cat. The pair are *different photographs of different dogs*, so a child
cannot solve the trial by matching pictures — they have to recognise that two things
that look unalike are the same kind, while a third that may look similar is not. That
is the complement of the vocab-gradient bank, which varies conceptual similarity while
holding one image per concept.

Needs the full THINGS image set (~12-20 exemplars per concept); the study's own
public/stimuli has only one image per concept, which is why these cannot be built
from it. Exemplars are chosen with CLIP:

  pair  - the two most visually *dissimilar* exemplars of the target concept that are
          both still typical of it, so the trial tests category and not appearance
  odd   - the most typical exemplar of the contrast concept, so it clearly depicts it

Run from repo root (CLIP weights load from the local HF cache, no network needed):
    python3 scripts/make_basic_level_trials.py
"""

import argparse
import io
import json
import os
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parent.parent
# images_THINGS.zip ships encrypted. Supply the password via THINGS_ZIP_PASSWORD (or
# --password) rather than committing it here. Falls back to the extracted folder beside
# the archive, which holds only the 72 child-centred BabyView concepts.
THINGS_ZIP = Path("/Users/brialong/Documents/GitHub/babyview-variability-learning/"
                  "data/things_images/images_THINGS.zip")
THINGS_DIR = THINGS_ZIP.parent / "object_images"
OUT_IMG = ROOT / "public" / "stimuli_basic"
OUT_JSON = ROOT / "public" / "basic_level_trials.json"
MODEL = "laion/CLIP-ViT-B-32-laion2B-s34B-b79K"
SIZE = 300          # match public/stimuli

# (target concept shown twice, contrast concept shown once, shared category, how
# close the contrast is). Both orders of a close pair appear so that the target is
# counterbalanced -- otherwise "the odd one is always the cat" is learnable.
PAIRS = [
    # animals
    ("dog",       "cat",        "animal",    "near"),
    ("cat",       "dog",        "animal",    "near"),
    ("horse",     "cow",        "animal",    "near"),
    ("pig",       "sheep",      "animal",    "near"),
    # birds
    ("duck",      "crow",       "bird",      "far"),
    ("crow",      "duck",       "bird",      "far"),
    ("owl",       "parrot",     "bird",      "near"),
    ("parrot",    "owl",        "bird",      "near"),
    # vehicles
    ("car",       "truck",      "vehicle",   "near"),
    ("truck",     "car",        "vehicle",   "near"),
    ("bus",       "train",      "vehicle",   "far"),
    ("airplane",  "helicopter", "vehicle",   "near"),
    # THINGS names the concept "bike", not "bicycle"
    ("bike",      "motorcycle", "vehicle",   "near"),
    ("bike",      "tricycle",   "vehicle",   "near"),
    # fruit
    ("apple",     "orange",     "fruit",     "near"),
    ("orange",    "apple",      "fruit",     "near"),
    ("banana",    "pear",       "fruit",     "far"),
    ("raspberry", "peach",      "fruit",     "near"),
    # furniture
    ("chair",     "table",      "furniture", "far"),
    ("table",     "chair",      "furniture", "far"),
    ("couch",     "mattress",   "furniture", "near"),
    ("dresser",   "stool",      "furniture", "far"),
    # tableware
    ("cup",       "glass",      "tableware", "near"),
    ("bowl",      "plate",      "tableware", "near"),
    ("spoon",     "fork",       "tableware", "near"),
    ("kettle",    "pan",        "tableware", "near"),
    # clothing
    ("shoe",      "boot",       "clothing",  "near"),
    ("boot",      "shoe",       "clothing",  "near"),
    ("pants",     "shorts",     "clothing",  "near"),
    ("hat",       "beanie",     "clothing",  "near"),
]


class Exemplars:
    """Concept -> list of exemplar images, from the encrypted archive when a password
    is available and from the extracted folder otherwise."""

    def __init__(self, password):
        self.zip = None
        if password and THINGS_ZIP.exists():
            self.zip = zipfile.ZipFile(THINGS_ZIP)
            self.zip.setpassword(password.encode())
            self.index = {}
            for n in self.zip.namelist():
                if n.lower().endswith(".jpg") and n.count("/") >= 2:
                    self.index.setdefault(n.split("/")[1], []).append(n)

    def get(self, c):
        if self.zip is not None:
            return sorted(self.index.get(c, []))
        d = THINGS_DIR / c
        return sorted(str(p) for p in d.glob("*.jpg")) if d.is_dir() else []

    def open(self, ref):
        if self.zip is not None:
            return Image.open(io.BytesIO(self.zip.read(ref))).convert("RGB")
        return Image.open(ref).convert("RGB")


def bank_concepts():
    """Concepts a child can already meet in a session. The manifest guarantees no
    concept repeats within a session, so a new tier must not reintroduce one."""
    mf = json.loads((ROOT / "public" / "manifest.json").read_text())
    seen = set()
    for k in ("intro", "core"):
        for t in mf.get(k) or []:
            seen.update(t["concepts"])
    for b in (mf.get("blocks") or [])[:mf["meta"]["active_blocks"]]:
        for t in b:
            seen.update(t["concepts"])
    return seen


def collect(concepts, ex):
    got = {}
    for c in concepts:
        paths = ex.get(c)
        if len(paths) < 4:
            raise SystemExit(
                f"'{c}' has {len(paths)} exemplars. Without the archive password only "
                f"the {len(list(THINGS_DIR.glob('*')))} extracted concepts are reachable; "
                "set THINGS_ZIP_PASSWORD to use the full set.")
        got[c] = paths
    return got


def singleton_scores(paths, concept, model, proc, device, ex):
    """How much each exemplar looks like ONE object rather than a pile of them.

    THINGS includes plenty of multi-object shots -- seven bottles in a row, a rack of
    hats. Those are fine for adults and confusing for a three-year-old, who may read
    "the odd one" as "the one where there are lots". CLIP's text tower separates
    singular from plural well enough to rank them out.
    """
    ims = [ex.open(p) for p in paths]
    prompts = [f"a photo of a single {concept}",
               f"a photo of one {concept} on a plain background",
               f"a photo of many {concept}s",
               f"a photo of a group of {concept}s"]
    with torch.no_grad():
        inp = proc(text=prompts, images=ims, return_tensors="pt",
                   padding=True).to(device)
        out = model(**inp)
        p_ = out.logits_per_image.softmax(dim=-1).cpu().numpy()
    return p_[:, :2].sum(axis=1) - p_[:, 2:].sum(axis=1)


def embed(paths, model, proc, device, ex):
    ims = [ex.open(p) for p in paths]
    with torch.no_grad():
        inp = proc(images=ims, return_tensors="pt").to(device)
        f = model.get_image_features(**inp)
    f = torch.nn.functional.normalize(f, dim=-1)
    return f.cpu().numpy()


def fit_square(im, dst, size=SIZE):
    """Letterbox onto white -- THINGS objects sit on white already, so this keeps the
    whole object visible at a fixed canvas size instead of cropping it."""
    im = im.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    canvas.save(dst, "JPEG", quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--password", default=os.environ.get("THINGS_ZIP_PASSWORD"),
                    help="password for images_THINGS.zip; or set THINGS_ZIP_PASSWORD")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    concepts = sorted({c for p in PAIRS for c in p[:2]})
    clash = sorted({c for p in PAIRS for c in p[:2]} & bank_concepts())
    if clash:
        raise SystemExit("these concepts already appear in the child bank and would "
                         f"repeat within a session: {clash}")
    ex = Exemplars(a.password)
    if True:
        print("source:", "full THINGS archive" if ex.zip else f"extracted {THINGS_DIR.name}/")
        pool = collect(concepts, ex)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"loading CLIP on {device} …")
        model = CLIPModel.from_pretrained(MODEL).to(device).eval()
        proc = CLIPProcessor.from_pretrained(MODEL)

        emb, typ, single = {}, {}, {}
        for c, paths in pool.items():
            e = embed(paths, model, proc, device, ex)
            emb[c] = e
            # typicality = mean similarity to the concept's other exemplars
            S = e @ e.T
            np.fill_diagonal(S, np.nan)
            typ[c] = np.nanmean(S, axis=1)
            single[c] = singleton_scores(paths, c, model, proc, device, ex)
            n_ok = int((single[c] > 0).sum())
            print(f"  {c:9} {len(paths):2d} exemplars, {n_ok:2d} read as a single object")

        OUT_IMG.mkdir(parents=True, exist_ok=True)
        for f in OUT_IMG.glob("*.jpg"):
            f.unlink()

        trials = []
        used = set()          # (concept, exemplar index) already spent on some trial
        for i, (tgt, odd, cat, dist) in enumerate(PAIRS):
            E, T, G = emb[tgt], typ[tgt], single[tgt]
            # Both pair items must read as the concept AND as one object; within that
            # window take the two that look least alike, so the trial cannot be solved
            # by matching pictures.
            free = np.array([j for j in range(len(T)) if (tgt, j) not in used])
            keep = np.array([j for j in free
                             if T[j] >= np.percentile(T, 35) and G[j] > 0])
            if len(keep) < 2:                       # relax, but never reuse an exemplar
                keep = free[np.argsort(-G[free])][:max(2, int((G[free] > 0).sum()))]
            if len(keep) < 2:
                raise SystemExit(f"ran out of unused exemplars for '{tgt}'")
            S = E @ E.T
            best, lo = None, 2.0
            for x in keep:
                for y in keep:
                    if x < y and S[x, y] < lo:
                        lo, best = S[x, y], (x, y)
            i1, i2 = best
            # Clearest single-object example of the contrast concept, again unused.
            od_free = [j for j in range(len(typ[odd])) if (odd, j) not in used]
            od_ok = [j for j in od_free if single[odd][j] > 0] or od_free
            if not od_ok:
                raise SystemExit(f"ran out of unused exemplars for '{odd}'")
            io = int(max(od_ok, key=lambda j: typ[odd][j]))
            used.update({(tgt, int(i1)), (tgt, int(i2)), (odd, io)})

            names = []
            for concept, idx in ((tgt, i1), (tgt, i2), (odd, io)):
                fn = f"{concept}_{int(idx):02d}.jpg"
                fit_square(ex.open(pool[concept][idx]), OUT_IMG / fn)
                names.append((fn, concept))

            order = list(range(3))
            rng.shuffle(order)
            names = [names[k] for k in order]
            odd_pos = [k for k, (_, c) in enumerate(names) if c == odd][0]
            cross = float(np.mean([E[i1] @ emb[odd][io], E[i2] @ emb[odd][io]]))

            trials.append({
                "trial_id": f"basic_{i:02d}",
                "tier": "basic_level",
                "dataset": "things_basic_level",
                "condition": f"{tgt}_vs_{odd}",
                "contrast_distance": dist,
                "n_objects": 3,
                "oddity_index": odd_pos,
                "images": [f"stimuli_basic/{n}" for n, _ in names],
                "concepts": [c for _, c in names],
                "odd_concept": odd,
                "pair_concepts": [tgt, tgt],
                "pair_category": cat,
                "odd_category": cat,
                # Two numbers worth keeping. clip_within_pair is how alike the two
                # same-concept images are: push it too high and a child can solve the
                # trial by matching pictures instead of categorising. Comparing it to
                # clip_pair_to_odd gives the same appearance-vs-concept contrast the
                # main bank manipulates: when the odd item looks *more* like a pair
                # member than the pair members look like each other, appearance and
                # category point in opposite directions.
                "clip_within_pair": round(float(S[i1, i2]), 3),
                "clip_pair_to_odd": round(cross, 3),
                "appearance": "congruent" if S[i1, i2] > cross else "conflict",
                "spose_sim_pair": None,
                "p_correct_spose": None,
                "vis_sim_pair": None,
                "vis_margin": None,
                "human_avg_adult": None,
                "rt_avg_adult": None,
                "difficulty_bin": f"basic_{dist}",
            })
            print(f"  {trials[-1]['trial_id']}  2x{tgt:7} vs {odd:7} "
                  f"within {S[i1,i2]:.3f} / cross {cross:.3f}  "
                  f"{trials[-1]['appearance']}")

        OUT_JSON.write_text(json.dumps({"basic_level": trials}, indent=1))
        print(f"\nwrote {OUT_JSON} — {len(trials)} trials")
        print(f"wrote {len(list(OUT_IMG.glob('*.jpg')))} images to {OUT_IMG}")

if __name__ == "__main__":
    main()

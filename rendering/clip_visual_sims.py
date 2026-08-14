"""Compute a full image x image CLIP similarity matrix over the vocab-gradient
paper's stimulus set.

The oddity trials here are meant to probe *visual* similarity structure, so
the selector has to be an image-level model. SPoSE is concept-level and mixes
conceptual dimensions into the space, and vocab-gradient only ever computed
CLIP similarities for the 120 published trials — not the full matrix. This
builds the full one.

Model is CLIP ViT-B/32 with OpenAI weights, matching
vocab-gradient/stimuli/2_get_all_clip_similarities/compute_clip_similarities.py
(`clip.load("ViT-B/32")`), so these similarities are on the same footing as
the ones in the paper.

Outputs:
    rendering/_derived/clip_image_sim.npy    float32 [n, n] cosine similarity
    rendering/_derived/clip_concepts.json    the n concept names, matching order

Run:  python3 rendering/clip_visual_sims.py
"""

import json
from pathlib import Path

import numpy as np
import torch
import open_clip
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
VG = Path("/Users/brialong/Documents/GitHub/vocab-gradient")
IMAGE_DIR = VG / "stimuli" / "3_selected_stimuli" / "images_final2023-11-09"
TEST_ITEMS = VG / "data" / "item_metadata" / "test_items.csv"

OUT_DIR = ROOT / "rendering" / "_derived"
OUT_SIM = OUT_DIR / "clip_image_sim.npy"
OUT_CONCEPTS = OUT_DIR / "clip_concepts.json"

BATCH = 64


def paper_concepts():
    """Every target and distractor in the published item set."""
    import pandas as pd
    ti = pd.read_csv(TEST_ITEMS)
    return set(ti["Word1"].dropna()) | set(ti["Word2"].dropna())


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    paper = paper_concepts()
    paths = sorted(p for p in IMAGE_DIR.glob("*.jpg") if p.stem in paper)
    names = [p.stem for p in paths]
    print(f"{len(paths)} images (paper concepts with a stimulus file)")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"loading CLIP ViT-B/32 (openai weights) on {device}…")
    # "ViT-B-32-quickgelu", not "ViT-B-32": the OpenAI checkpoint was trained
    # with QuickGELU activations, and open_clip's plain ViT-B-32 config uses
    # standard GELU. Loading the openai tag under the plain config silently
    # produces slightly wrong features (it warns, and the warning is right).
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32-quickgelu", pretrained="openai")
    model = model.to(device).eval()

    feats = []
    with torch.no_grad():
        for i in range(0, len(paths), BATCH):
            batch = paths[i:i + BATCH]
            px = torch.stack([preprocess(Image.open(p).convert("RGB")) for p in batch]).to(device)
            f = model.encode_image(px).float()
            f = f / f.norm(dim=-1, keepdim=True)
            feats.append(f.cpu())
            print(f"  {min(i + BATCH, len(paths))}/{len(paths)}")
    feats = torch.cat(feats)

    sim = (feats @ feats.T).numpy().astype(np.float32)
    np.save(OUT_SIM, sim)
    OUT_CONCEPTS.write_text(json.dumps(names, indent=1))

    off = sim[~np.eye(len(sim), dtype=bool)]
    print(f"\nsimilarity matrix {sim.shape}")
    print(f"off-diagonal: min {off.min():.3f}  mean {off.mean():.3f}  max {off.max():.3f}")
    print(f"wrote {OUT_SIM}\nwrote {OUT_CONCEPTS}")

    # Sanity check: nearest visual neighbours for a few concepts.
    idx = {n: i for i, n in enumerate(names)}
    for probe in ["orange", "carrot", "boat", "pizza"]:
        if probe not in idx:
            continue
        row = sim[idx[probe]].copy()
        row[idx[probe]] = -1
        top = np.argsort(-row)[:5]
        print(f"  {probe:<8} -> " + ", ".join(f"{names[j]} ({row[j]:.2f})" for j in top))


if __name__ == "__main__":
    main()

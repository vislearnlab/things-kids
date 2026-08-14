# Rotation animation pipeline

State of play, after inspecting `tzler/mochi_code` and the Hugging Face
sources:

| asset | source | available? | path |
| --- | --- | --- | --- |
| shapenet pre-rendered images | HF `tzler/MOCHI` | yes (already downloaded) | `MOCHI/data/train-*.parquet` |
| shapegen pre-rendered images | HF `tzler/MOCHI` | yes (already downloaded) | same parquet |
| **shapenet 3D meshes** | HF `ShapeNet/shapenetcore-glb` | **gated — needs HF auth + ShapeNet ToS accepted** | (you'll download to `./meshes/`) |
| **shapegen 3D meshes / pipeline** | not in mochi_code repo | **needs author contact (Bonnen)** | (see `email_to_bonnen.txt`) |
| majaj 3D meshes (HVM animals/chairs) | DiCarlo lab / Brain-Score | available with effort | not yet wired |
| barense | not used (excluded) | n/a | n/a |

Realistic plan: render rotation flipbooks for the 39 shapenet trials this
week, ask Bonnen for shapegen, render those when received.

## What's in this folder

`build_needed_list.py` — Reads the curated trial manifest + the MOCHI
parquet, and produces `needed_shapenet.json` listing the 76 unique
(category, model_id) pairs we need from ShapeNetCore. Run once.

`download_shapenet.py` — Downloads only those 76 GLB files from the
HF gated repo. Requires `HF_TOKEN`. Total disk ~100 MB depending on mesh
density.

`render_rotations.py` — pyrender pipeline. 13 frames per object at
+/-45 deg yaw, smooth ease-in-out, ortho camera, two directional lights,
transparent background. Saves to `./rotation_frames/<cat>/<mid>/00.png …
12.png`. Requires `libosmesa6-dev` or working EGL on Linux.

`render_blender.py` — Same job, alternate stack. Use this on macOS or any
machine where pyrender's GL setup is annoying. Run as
`blender --background --python render_blender.py -- ...`.

`poc_rotation.gif` and `poc_frames/` — proof-of-concept on a procedural
blob mesh, generated via numpy + matplotlib (no GL required). Confirms the
geometry / interpolation logic is correct.

`email_to_bonnen.txt` — Draft to send Tyler Bonnen for shapegen meshes.

## End-to-end commands once you have HF auth

```bash
# 1. enumerate what we need
python build_needed_list.py \
    --mochi /path/to/MOCHI/data/train-00000-of-00001.parquet \
    --manifest ../public/manifest.json \
    --out needed_shapenet.json

# 2. accept ShapeNet ToS at huggingface.co/datasets/ShapeNet/shapenetcore-glb
#    then create token at huggingface.co/settings/tokens
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx

# 3. download
python download_shapenet.py --needed needed_shapenet.json --out ./meshes

# 4. render rotations (pyrender)
python render_rotations.py --meshes ./meshes --out ./rotation_frames

#    OR (blender)
blender --background --python render_blender.py -- \
    --meshes ./meshes --out ./rotation_frames
```

## Wiring into the game

Once frames exist at `rendering/rotation_frames/<cat>/<mid>/{00..12}.png`,
update `public/manifest.json` to add an `images_animated` field per trial
that points to the 13-frame folder, then in `index.html` swap the static
`<img>` for a CSS keyframe sequence cycling through the 13 frames at
~12 fps (forward and reverse, ping-pong loop). The trial logic, click
handler, scoring, and data pipeline are unchanged — animated and static
trials produce the same data shape.

A clean experimental design within-subjects: random half of trials show
the static still (current behavior), the other half show the rotation
flipbook. Counterbalance across participants by a URL param like
`?cond=A` vs `?cond=B`.

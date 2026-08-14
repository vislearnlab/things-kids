"""
Validate the static site's data integrity:
  - manifest.json is valid JSON, each trial has the required fields
  - every image path referenced in manifest exists on disk
  - every referenced image is a real image (PIL can open it)
  - every Zorpie GIF used by index.html exists

Run:
    python tests/check_assets.py
"""
import json, os, sys, re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# Vite's `publicDir` is `public/` and contents are copied to `dist/` at
# build time. Static-data checks (manifest, stimuli, mascot images) run
# against `public/`, which is the source of truth.
PUBLIC = PROJECT / 'public'

REQUIRED_TRIAL_FIELDS = {'trial_id', 'tier', 'dataset', 'condition',
                         'n_objects', 'oddity_index', 'images', 'human_avg_adult'}
ALLOWED_TIERS = {'training', 'warmup', 'familiar', 'novel', 'catch'}

errors = []

def fail(msg):
    errors.append(msg)
    print(f"  FAIL  {msg}")

def ok(msg):
    print(f"  ok    {msg}")

def check_manifest():
    print("==> manifest.json")
    p = PUBLIC / 'manifest.json'
    if not p.exists():
        fail("manifest.json missing"); return None
    try:
        m = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        fail(f"manifest.json invalid JSON: {e}"); return None
    if 'trials' not in m or not isinstance(m['trials'], list):
        fail("manifest must have a 'trials' list"); return None
    ok(f"loaded {len(m['trials'])} trials")
    return m

def check_trial_schema(trials):
    print("==> trial schema")
    bad = 0
    for i, t in enumerate(trials):
        missing = REQUIRED_TRIAL_FIELDS - set(t.keys())
        if missing:
            fail(f"trial[{i}] {t.get('trial_id', '?')} missing: {missing}")
            bad += 1
            continue
        if t['tier'] not in ALLOWED_TIERS:
            fail(f"trial[{i}] {t['trial_id']} bad tier: {t['tier']}")
            bad += 1
        if not isinstance(t['images'], list) or len(t['images']) != t['n_objects']:
            fail(f"trial[{i}] {t['trial_id']} images count != n_objects")
            bad += 1
        if not (0 <= t['oddity_index'] < t['n_objects']):
            fail(f"trial[{i}] {t['trial_id']} oddity_index out of range")
            bad += 1
    if bad == 0: ok(f"all {len(trials)} trials have valid schema")

def check_images_exist(trials):
    print("==> image files exist")
    missing = []
    for t in trials:
        for img in t['images']:
            p = PUBLIC / img
            if not p.exists():
                missing.append(img)
    if missing:
        for m in missing[:10]: fail(f"missing image: {m}")
        if len(missing) > 10: fail(f"... and {len(missing)-10} more")
    else:
        ok(f"all {sum(len(t['images']) for t in trials)} images present")

def check_images_loadable(trials):
    print("==> images load with PIL")
    try:
        from PIL import Image
    except ImportError:
        print("  skipped (PIL not installed)")
        return
    bad = 0
    for t in trials:
        for img in t['images']:
            p = PUBLIC / img
            if not p.exists():
                continue  # already counted
            try:
                with Image.open(p) as im:
                    im.verify()
            except Exception as e:
                fail(f"{img}: {e}")
                bad += 1
    if bad == 0: ok("all images loadable")

def check_html_assets():
    print("==> assets referenced from src/survey/experiment.ts")
    src = (PROJECT / 'src' / 'survey' / 'experiment.ts').read_text()
    refs = set(re.findall(r'images/[\w/]+\.(?:gif|png|jpg|jpeg|svg)', src))
    refs |= set(re.findall(r"audio/[\w/]+\.mp3", src))
    # also check the root index.html for any direct references
    if (PROJECT / 'index.html').exists():
        h = (PROJECT / 'index.html').read_text()
        refs |= set(re.findall(r'images/[\w/]+\.(?:gif|png|jpg|jpeg|svg)', h))
        refs |= set(re.findall(r"audio/[\w/]+\.mp3", h))
    miss = []
    for r in refs:
        if not (PUBLIC / r).exists():
            miss.append(r)
    if miss:
        for m in miss: fail(f"experiment references missing file: {m}")
    else:
        ok(f"all {len(refs)} experiment-referenced assets present")

def main():
    m = check_manifest()
    if m is None: sys.exit(1)
    check_trial_schema(m['trials'])
    check_images_exist(m['trials'])
    check_images_loadable(m['trials'])
    check_html_assets()
    print()
    if errors:
        print(f"FAILED — {len(errors)} problems")
        sys.exit(1)
    print("PASSED — assets are clean")

if __name__ == '__main__':
    main()

# tests/

Three things live here.

`check_assets.py` — static integrity. Validates `public/manifest.json`
schema, confirms every image referenced exists on disk and opens cleanly
with PIL, and checks every `images/.../<file>` referenced by `index.html`
also exists.

`e2e_playthrough.py` — Playwright end-to-end. Boots a local
`python -m http.server` against `public/`, then in headless Chromium:
1. confirms the disabled `LET'S PLAY` button on the consent screen
   blocks advancing without age + checkbox,
2. plays through every trial clicking the correct card and asserts
   `n_trials == n_correct == manifest length`, no console errors,
   no failed requests, all trials have `rt` and `trial_id`,
3. stress-tests the `{once: true}` click listener with a rapid
   double-click — exactly one trial should finalize.

`run_all.sh` — runs static checks (`node --check` on inline JS and
`server/server.js`, `python -m compileall` on helpers, `check_assets.py`)
followed by `e2e_playthrough.py`. Used by CI and by `make test`.

## Running locally

```bash
pip install playwright pillow pyarrow pandas
python -m playwright install chromium
bash tests/run_all.sh
```

## What we don't test here yet

Server `/submit` against MongoDB (skipped because it needs Mongo running),
mobile viewport, Safari, audio playback (Web Audio chime is hard to
introspect headless). See `TESTING.md` at the repo root for the full
strategy.

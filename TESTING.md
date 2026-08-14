# Testing strategy

The repo ships with three layers of automated checks. CI runs all of them
on every push to `main` via `.github/workflows/test.yml`.

## Layer 1 — static checks

Cheapest and fastest. No browser, no servers.

| check | tool | what it catches |
| --- | --- | --- |
| Inline JS syntax in `index.html` | `node --check` | typos, missing brackets, bad arrow-fn syntax |
| Server JS syntax | `node --check server/server.js` | same, on the Node side |
| Python syntax (rendering, tests) | `python -m compileall` | typos in helper scripts |
| Manifest schema | `tests/check_assets.py` | every trial has the required fields, image paths resolve |
| Stimulus integrity | `tests/check_assets.py` | every image referenced in manifest exists on disk and is a valid JPEG/PNG |

## Layer 2 — end-to-end (Playwright)

`tests/e2e_playthrough.py` boots the static site and drives a real headless
Chromium through the whole experiment. Specifically:

- Loads `index.html` over a local `python -m http.server`
- Verifies the consent screen blocks `LET'S PLAY` until both age and
  checkbox are set
- Plays through *all* curated trials, clicking the correct card each time,
  and confirms the final downloaded data has `n_trials == n_correct ==`
  the manifest length
- Plays a second pass clicking *wrong* cards and verifies `correct=false`
  is recorded
- Stress-tests the trial click handler with a rapid double-click and
  asserts only one trial is finalized (the `{once: true}` listener)
- Captures all `console.error` and failed network requests; any non-empty
  list fails the test

## Layer 3 — server smoke tests

`tests/test_server.mjs` boots the Express server against a temporary
in-process MongoDB stand-in (`mongodb-memory-server`) and POSTs:

- A well-formed payload → expects `{ok: true}` and an upserted document
- A second payload with the same `participantID` → expects update, not
  insert (matches the `Insert(data, participantID, 'participantID')`
  upsert convention)
- A payload missing `participantID` → expects `400`
- A 15 MB payload → expects to either succeed or 413, but not crash

## What we don't (yet) test

- Mobile viewport rendering — manual for now
- Audio playback — Web Audio chime can't be verified in headless Chromium
  reliably; we just confirm `audioCtx` is created without errors
- The rendering pipeline (`rendering/render_rotations.py`) — depends on
  ShapeNet meshes that are gated and not in CI
- Cross-browser (Safari, Firefox) — Playwright can run them but it costs
  CI minutes; revisit if we see browser-specific issues in pilots

## How to run locally

```bash
# all of layer 1 + layer 2 (no MongoDB needed)
make test           # or:  bash tests/run_all.sh

# specific
node --check public/index.html        # quick JS check
python tests/check_assets.py          # asset integrity
python tests/e2e_playthrough.py       # Playwright e2e

# server (requires Node + npm install in tests/)
cd tests && npm install && npm test
```

## Continuous integration

The repo has two workflows under `.github/workflows/`:

**`test.yml`** — runs on every push and PR to `main`:

1. Checkout
2. Set up Node 20 + Python 3.11
3. Install Playwright + chromium
4. Run `bash tests/run_all.sh`
5. Fail the workflow on any error

**`pages.yml`** — builds and deploys the static site to GitHub Pages on
every push to `main`. Uploads `public/` as the artifact and runs
`actions/deploy-pages@v4`. After the first run, the site lives at
`https://vislearnlab.github.io/mochi-kids/`.

### Recommended branch protection (set in repo Settings → Branches)

- Require PR before merging to `main`
- Require status checks to pass (`test` from `test.yml`)
- Require branches to be up-to-date before merging
- (Optional) Require linear history

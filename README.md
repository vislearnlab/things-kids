# MOCHI Kids — Shape Detective

A kid-friendly (4–6 year olds) adaptation of the MOCHI 3D-shape oddity
benchmark (Bonnen et al., NeurIPS 2024 D&B). Three-image trials: two
views of the same object, one different — tap the odd one out.

Live demo: **https://vislearnlab.github.io/mochi-kids/**

[![tests](https://github.com/vislearnlab/mochi-kids/actions/workflows/test.yml/badge.svg)](https://github.com/vislearnlab/mochi-kids/actions/workflows/test.yml)
[![pages](https://github.com/vislearnlab/mochi-kids/actions/workflows/pages.yml/badge.svg)](https://github.com/vislearnlab/mochi-kids/actions/workflows/pages.yml)

## Quick start

```bash
# play it locally
make serve                  # or: cd public && python3 -m http.server 8000

# run all tests
make test
```

Or double-click `start.command` from Finder on macOS.

## What's here

```
mochi-kids/
├── public/                    # the static site GH Pages serves   → public/README.md
│   ├── index.html             # single-file jsPsych v8 experiment
│   ├── manifest.json          # 80 curated trials
│   ├── stimuli/<trial>/0..2.jpg
│   ├── audio/                 # 3 gTTS prompts (welcome / how_to_play / reminder)
│   └── images/zorpie/         # mascot GIFs (from vislearnlab/museumkiosk)
├── server/                    # optional Express + MongoDB save layer  → server/README.md
├── rendering/                 # rotation-animation pipeline (planned)  → rendering/README.md
├── tests/                     # asset-integrity + Playwright e2e       → tests/README.md
├── docs/                      # research artifacts (figures, sims)     → docs/README.md
├── .github/workflows/         # CI (test) + GH Pages (pages)           → .github/README.md
├── TESTING.md                 # full testing strategy
├── start.command              # double-click → serves locally + opens browser
└── push_to_vislearnlab.command  # one-click: gh repo create + push + enable Pages
```

## Trial set (80 trials, gray-render only)

| tier | n | dataset | content | mean adult acc |
| --- | --- | --- | --- | --- |
| training | 12 | synthesized | same image × 2 + 1 different image (pop-out) | trivial |
| warmup | 12 | shapenet | easiest chair / lamp / bench | 1.00 |
| familiar | 28 | shapenet | 8 categories: chair, lamp, bench, telephone (4 each) + car, airplane, sofa, table (3 each) | 0.97 |
| novel | 28 | shapegen | random sample from `abstract4`/`abstract3`/`abstract2` | 0.91 |

Familiar and novel each split into 2 sub-blocks at runtime; the four
sub-blocks play in random order after warmup. Each block opens with a
short Zorpie intro screen.

Each manifest entry preserves `human_avg_adult` and `rt_avg_adult`
so calibration analyses can use them directly. See
[`public/stimuli/README.md`](public/stimuli/README.md) for the curate
logic and re-run instructions.

## Audio + reward design

Spoken voice fires at three structured moments only — never per-trial,
so the soundscape stays calm:

| when | what plays |
| --- | --- |
| Consent screen | `welcome.mp3` |
| How-to-play | `how_to_play.mp3` |
| Every 10 trials (`?reminder_every=N`) | `reminder.mp3` |

Reward audio = **chime only**. A C-major arpeggio synthesized live via
Web Audio API on every correct answer. No sound on wrong (no harsh
buzzer). 16-particle multicolor sparkle burst from the correct card.
HUD score pill ticks up with a small pop animation. End screen shows
Zorpie + a count of correct answers (no star rating).

The voice files were generated with gTTS — they're functional but
robotic. Drop in real recordings at the same filenames in
`public/audio/` to upgrade with no code changes.

## URL parameters

| param | default | what it does |
| --- | --- | --- |
| `participantID` | random `kid_xxxxxxxx` | Prolific / SONA / lab ID |
| `study` | `mochi_kids_v1` | Study tag stored with the record |
| `save` | `true` (auto-`false` on `*.github.io`/`*.web.app`/etc.) | Set to `false` to skip POST |
| `submit_url` | `/submit` | Override server endpoint |
| `reminder_every` | `10` | Trials between spoken reminders |
| `break_every` | `20` | Trials between break screens |

Example: `https://vislearnlab.github.io/mochi-kids/?participantID=pilot01`

## Data shape

Each completed session POSTs (or the kid downloads) one JSON document:

```json
{
  "participantID": "kid_xxxx",
  "study": "mochi_kids_v1",
  "consent": { "age": "6", "agreed": true },
  "n_trials": 80, "n_correct": 64, "mean_rt": 3145.2,
  "trials": [{ "task": "mochi_oddity", "trial_id": "shapenet1234",
               "tier": "familiar", "condition": "chair",
               "correct": true, "rt": 2810.4,
               "oddity_index_orig": 1, "chosen_orig_index": 1,
               "display_order": [2, 0, 1], ... }]
}
```

When running via GitHub Pages (no server), the user gets a
"Download my data" button on the end screen. When running with the
Express server (`cd server && npm start`), the same payload is
upserted to MongoDB on `participantID`.

## Testing

CI runs the full suite on every push to `main`. Three layers:

1. **Static** — JS syntax (`node --check`), Python compile, manifest
   schema + image existence checks
2. **End-to-end** — Playwright drives a real headless Chromium through
   the entire experiment (consent, all 80 trials, breaks, reminders,
   end screen) and asserts no console errors, all RTs captured,
   double-clicks ignored
3. **Server** *(optional, planned)* — supertest against `/submit` with
   in-memory MongoDB

Locally: `make test` or `bash tests/run_all.sh`.

Full strategy: [TESTING.md](TESTING.md).

## Deploying

- **GitHub Pages** (no server) — `git push` to `main`. The
  `pages.yml` workflow publishes `public/` automatically. Live URL:
  `https://vislearnlab.github.io/mochi-kids/`.
- **Lab server** (with MongoDB save) — see
  [`server/README.md`](server/README.md).

The static client auto-disables `/submit` POSTs on `*.github.io`,
`*.web.app`, and similar hosts so it works offline / read-only on Pages.

## Roadmap

- [x] Static play-through w/ jsPsych v8, kid-friendly UX
- [x] Curated 80-trial easy-tail set (familiar real objects + novel
      abstract shapes)
- [x] Consent + age picker, scoped audio (welcome, how-to-play, every
      10-trial reminder)
- [x] CI + automated tests, GH Pages deploy
- [ ] Real pilot — N≈30 kids per age (4, 5, 6) + matched adult sample
- [ ] Rotation-animation manipulation (within-subjects ±45° yaw on a
      random half of trials — waiting on ShapeNet GLB access and
      shapegen meshes from Bonnen; see
      [`rendering/README.md`](rendering/README.md))
- [ ] Pre-registration of the human-model crossover hypothesis (kids
      beat models on familiar real objects, models beat kids on novel
      abstracts — see `docs/simulated_results.png` for the predicted
      pattern)
- [ ] Replace gTTS prompts with a real recorded voice

## Citation

If you publish work using this code or stimuli, please cite the MOCHI
benchmark:

```
Bonnen, T., Fu, S., Bai, Y., O'Connell, T., Friedman, Y., Kanwisher, N.,
Tenenbaum, J. B., & Efros, A. A. (2024). Evaluating Multiview Object
Consistency in Humans and Image Models. NeurIPS Datasets & Benchmarks.
arXiv:2409.05862.
```

## Acknowledgments

Mascot art (Zorpie) from
[brialorelle/museumkiosk](https://github.com/brialorelle/museumkiosk).
Stimuli from [tzler/MOCHI](https://huggingface.co/datasets/tzler/MOCHI)
on Hugging Face. Schoolbell font from Google Fonts. jsPsych v8.

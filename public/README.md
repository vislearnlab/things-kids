# public/

The static site that GitHub Pages serves. Open `index.html` through any
HTTP server (not `file://`) and the experiment runs.

## Layout

```
public/
├── index.html            # the whole game (single file, no build step)
├── manifest.json         # 35 curated trials + metadata
├── stimuli/<trial_id>/0.jpg, 1.jpg, 2.jpg
├── images/zorpie/        # Zorpie mascot GIFs (from vislearnlab/museumkiosk)
└── .nojekyll             # tells GitHub Pages not to run Jekyll on this folder
```

## How `index.html` is structured

Single-file jsPsych v8 experiment. Imports jsPsych + the
`html-button-response`, `html-keyboard-response`, and `preload` plugins
from unpkg, plus the Schoolbell font from Google Fonts. Then a single
`<script>` block:

1. URL-param + helper utilities (participant ID, save toggle, etc.)
2. `playChime()` — synthesized C-major arpeggio via Web Audio API. The
   only reward sound. No spoken voice anywhere.
3. `emitSparkles()`, `bumpScore()` — visual rewards on correct
4. `makeOddityTrial(t, i, N)` — builds a 3AFC trial: shuffles display
   order, attaches per-card click listeners with `{once: true}` so
   double-clicks don't double-finalize, records `correct`, `rt`,
   `display_order`, `chosen_orig_index`, etc.
5. `consentTrial()` — age picker + checkbox + collapsible consent text.
   The `LET'S PLAY` button stays disabled until both age and checkbox
   are set.
6. `main()` — fetches `manifest.json`, builds the timeline (preload →
   consent → how-to-play → trials with reminders every 10 / breaks
   every 20), runs jsPsych.

A boot overlay catches early failures (file:// origin, missing
manifest, JS errors) and shows them on screen instead of a blank page.

## URL parameters

| param | default | what it does |
| --- | --- | --- |
| `participantID` | random `kid_xxxxxxxx` | Prolific / SONA / lab ID |
| `study` | `mochi_kids_v1` | Study tag stored with the record |
| `save` | `true` (or `false` on `*.github.io`/`*.web.app`/etc.) | Set to `false` to skip POST |
| `submit_url` | `/submit` | Override server endpoint |
| `reminder_every` | `10` | Trials between spoken reminders |
| `break_every` | `20` | Trials between break screens |

Example: `https://vislearnlab.github.io/mochi-kids/?participantID=pilot01`

## Saved trial data shape

Each oddity trial saves:

```json
{
  "task": "mochi_oddity",
  "trial_id": "shapenet1234",
  "dataset": "shapenet",
  "condition": "chair",
  "tier": "familiar",
  "n_objects": 3,
  "oddity_index_orig": 1,
  "chosen_orig_index": 1,
  "chosen_display_pos": 2,
  "display_order": [2, 0, 1],
  "correct": true,
  "rt": 2810.4,
  "human_avg_adult": 1.0,
  "score_after": 14
}
```

Plus a top-level `consent: { age, agreed }` and a `summary` rolled up
in `on_finish`.

## Running locally (no build step)

```bash
# from the repo root
cd public
python3 -m http.server 8000
open http://localhost:8000/?save=false
```

Or double-click `start.command` in the project root.

## Deployment

CI publishes this folder to GitHub Pages on every push to `main` via
`.github/workflows/pages.yml`. Live URL after first deploy:
`https://vislearnlab.github.io/mochi-kids/`.

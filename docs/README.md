# docs/

Research artifacts — figures and simulated data for the eventual paper.
None of this is part of the runtime experiment.

## Files

`trial_selection.png` — 4-panel justification of the curated trial set
against the full MOCHI distribution: where on the difficulty axis we
sampled (panel A), which conditions were kept vs dropped with the .80
adult-accuracy floor (B), in-game difficulty trajectory across the 35
trials in playing order (C), and RT vs accuracy with picks highlighted
(D).

`simulated_results.png` — predicted per-tier accuracy for 4yo, 5yo,
6yo, adults, and the three foundation models (DINOv2-G, CLIP-L, MAE-H).
Humans are simulated (N=20 per group); models are real MOCHI
benchmark.csv scores on the curated trials. The headline finding the
plot surfaces: a *crossover* on familiar real objects (kids beat models)
that flips to model-better on novel abstract shapes.

`simulated_data.csv` — long-format session-level data backing the
above (subject × trial × correct × rt × tier × condition). 2,800 rows.
Use this for sanity-checking analysis pipelines before real data lands.

## Reproducing

The simulation script and curate script are not committed (they were
one-off ad-hoc analyses). The figures were produced by Python +
matplotlib using `tzler/MOCHI`'s parquet for ground-truth model scores
and a per-tier-floor logistic generative model for kid/adult
performance. Re-running should be straightforward; the parameter table
lives in the chat history that produced these figures.

If you want to bring that script back into version control, add a
`scripts/simulate.py` that reads `public/manifest.json` +
`mochi_code/assets/benchmark.csv` and writes both figures + the CSV.

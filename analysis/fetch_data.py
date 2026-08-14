"""Pull all sessions from the lab Mongo collection and flatten to CSV.

Run from repo root:
    python3 analysis/fetch_data.py

Reads connection info from .env. Writes:
    analysis/data/sessions.csv   one row per participant
    analysis/data/trials.csv     one row per trial (long format)
    analysis/data/raw.json       raw documents
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

OUT = ROOT / "analysis" / "data"
OUT.mkdir(parents=True, exist_ok=True)

MONGO_URL = os.environ["MONGO_URL"]
DATABASE = os.environ.get("DATABASE", "mochi_kids")
COLLECTION = os.environ.get("COLLECTION", "trials")

client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=8000)
coll = client[DATABASE][COLLECTION]

# Skip probe / debug docs whose participantID starts with "__".
docs = list(coll.find({"participantID": {"$not": {"$regex": "^__"}}}))
print(f"fetched {len(docs)} sessions from {DATABASE}.{COLLECTION}")


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


with open(OUT / "raw.json", "w") as f:
    json.dump(docs, f, indent=2, default=_json_default)

session_rows = []
trial_rows = []
for d in docs:
    pid = d.get("participantID")
    consent = d.get("consent") or {}
    screen = d.get("screen") or {}
    session_rows.append({
        "participantID": pid,
        "study": d.get("study"),
        "consent_age": consent.get("age"),
        "consent_agree": consent.get("agree"),
        "finishedAt": d.get("finishedAt"),
        "n_trials": d.get("n_trials"),
        "n_correct": d.get("n_correct"),
        "mean_rt": d.get("mean_rt"),
        "ua": d.get("ua"),
        "screen_w": screen.get("w"),
        "screen_h": screen.get("h"),
        "screen_dpr": screen.get("dpr"),
    })
    for i, t in enumerate(d.get("trials") or []):
        trial_rows.append({
            "participantID": pid,
            "consent_age": consent.get("age"),
            "trial_index": i,
            "trial_id": t.get("trial_id"),
            "tier": t.get("tier"),
            "dataset": t.get("dataset"),
            "condition": t.get("condition"),
            "n_objects": t.get("n_objects"),
            "oddity_index_orig": t.get("oddity_index_orig"),
            "chosen_orig_index": t.get("chosen_orig_index"),
            "chosen_display_pos": t.get("chosen_display_pos"),
            "correct": t.get("correct"),
            "rt": t.get("rt"),
            "human_avg_adult": t.get("human_avg_adult"),
            "rt_avg_adult": t.get("rt_avg_adult"),
            "score_after": t.get("score_after"),
        })

SESSION_COLS = [
    "participantID", "study", "consent_age", "consent_agree", "finishedAt",
    "n_trials", "n_correct", "mean_rt", "ua",
    "screen_w", "screen_h", "screen_dpr",
]
TRIAL_COLS = [
    "participantID", "consent_age", "trial_index", "trial_id", "tier",
    "dataset", "condition", "n_objects", "oddity_index_orig",
    "chosen_orig_index", "chosen_display_pos", "correct", "rt",
    "human_avg_adult", "rt_avg_adult", "score_after",
]

# ============ QA: session-level flags for bad-actor filtering ============
# Thresholds (lenient to avoid false-flagging real kids).
POSITION_SHARE_MAX = 0.60      # >60% on one position = position-spam
FAST_MS = 500                  # button-mash threshold
STUCK_MS = 15000               # disengaged threshold
MASH_RATE_MAX = 0.20           # >20% fast trials = mashing
TRAINING_MIN_ACC = 1.00        # pop-out training trials must all be correct
ACC_MIN = 0.40                 # overall acc must beat this (chance = 1/3)
RUN_LEN_MAX = 8                # longest streak of same-position picks tolerated

trials_df = pd.DataFrame(trial_rows, columns=TRIAL_COLS)
sessions_df = pd.DataFrame(session_rows, columns=SESSION_COLS)


def _max_run_length(seq):
    best = cur = 1
    prev = None
    for x in seq:
        if x == prev:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
        prev = x
    return best if seq else 0


qa_rows = []
for pid, g in trials_df.groupby("participantID"):
    n = len(g)
    pos_counts = g["chosen_display_pos"].value_counts(normalize=True)
    max_share = pos_counts.max() if len(pos_counts) else 0.0
    n_fast = int((g["rt"] < FAST_MS).sum())
    n_stuck = int((g["rt"] > STUCK_MS).sum())
    train = g[g["tier"] == "training"]
    train_acc = train["correct"].mean() if len(train) else 1.0
    catches = g[g["tier"] == "catch"]
    catch_acc = catches["correct"].mean() if len(catches) else 1.0
    overall_acc = g["correct"].mean() if n else 0.0
    run_len = _max_run_length(list(g.sort_values("trial_index")["chosen_display_pos"]))
    flags = {
        "qa_position_spam": max_share > POSITION_SHARE_MAX,
        "qa_mash":          (n / max(n, 1)) and (n_fast / max(n, 1) > MASH_RATE_MAX),
        "qa_pop_out_fail":  train_acc < TRAINING_MIN_ACC,
        "qa_catch_fail":    catch_acc < TRAINING_MIN_ACC,
        "qa_low_acc":       overall_acc < ACC_MIN,
        "qa_long_run":      run_len > RUN_LEN_MAX,
    }
    qa_rows.append({
        "participantID": pid,
        "max_position_share": round(max_share, 3),
        "max_run_length": run_len,
        "n_fast_lt_500ms": n_fast,
        "n_stuck_gt_15s": n_stuck,
        "training_acc": round(train_acc, 3),
        "catch_acc": round(catch_acc, 3),
        "overall_acc": round(overall_acc, 3),
        **{k: bool(v) for k, v in flags.items()},
        "qa_pass": not any(flags.values()),
    })

qa_df = pd.DataFrame(qa_rows)
sessions_df = sessions_df.merge(qa_df, on="participantID", how="left")

sessions_df.to_csv(OUT / "sessions.csv", index=False)
trials_df.to_csv(OUT / "trials.csv", index=False)
print(f"wrote {OUT}/sessions.csv ({len(session_rows)} rows)")
print(f"wrote {OUT}/trials.csv ({len(trial_rows)} rows)")
client.close()

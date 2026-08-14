"""Four-panel summary of the adult Prolific data.

Run:  python3 analysis/fetch_data.py && python3 analysis/adult_figure.py
Writes docs/adult_pilot.png
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "analysis" / "data"
OUT = ROOT / "docs" / "adult_pilot.png"

# Slots 1 and 2 of the validated categorical palette; neutrals for ink and grid.
OBS, PRED = "#2a78d6", "#eb6834"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#dcdcd8"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "font.size": 9, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "xtick.major.size": 0, "ytick.major.size": 0,
})

PROLIFIC_ID = re.compile(r"^[0-9a-f]{24}$")
sessions = pd.read_csv(DATA / "sessions.csv")
trials = pd.read_csv(DATA / "trials.csv")

manifest = json.loads((ROOT / "public" / "manifest.json").read_text())
meta = manifest["meta"]
rows = []
for key in ("intro", "core", "blocks", "adult_blocks"):
    for item in manifest.get(key) or []:
        for t in (item if isinstance(item, list) else [item]):
            rows.append({"trial_id": t["trial_id"],
                         "p_correct_spose": t.get("p_correct_spose")})
items = pd.DataFrame(rows).drop_duplicates("trial_id").set_index("trial_id")

sessions["is_prolific"] = sessions.participantID.astype(str).str.match(PROLIFIC_ID)
finished = (sessions.complete.fillna(False).astype(bool)
            | sessions.complete_inferred.fillna(False).astype(bool)
            | sessions.finishedAt.notna())
usable = sessions[sessions.is_prolific & sessions.qa_pass.fillna(False) & finished]
d = trials[trials.participantID.isin(usable.participantID)].join(items, on="trial_id")
test = d[d.tier.isin(["familiar", "warmup"])].dropna(subset=["p_correct_spose"]).copy()


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p, dd = k / n, 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / dd
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / dd
    return (max(0.0, c - h), min(1.0, c + h))


fig, axes = plt.subplots(2, 2, figsize=(10, 7.2))
fig.suptitle(f"THINGS-Kids adult reference sample — {len(usable)} Prolific adults, "
             f"{len(d)} trials (2026-08-14)",
             fontsize=11.5, fontweight="bold", x=0.055, ha="left", y=0.975)

# ---- A. observed vs predicted difficulty -------------------------------
ax = axes[0, 0]
test["bin"] = pd.qcut(test.p_correct_spose, 4, duplicates="drop")
g = test.groupby("bin", observed=True)
x = np.arange(len(g))
obs = g.correct.mean().values
pred = g.p_correct_spose.mean().values
cis = [wilson(int(gg.correct.sum()), len(gg)) for _, gg in g]
err = np.array([[o - lo for o, (lo, _) in zip(obs, cis)],
                [hi - o for o, (_, hi) in zip(obs, cis)]])

ax.axhline(1 / 3, color=GRID, lw=1, ls=(0, (4, 3)), zorder=1)
ax.text(len(x) - 0.55, 1 / 3 + 0.012, "chance", color=INK2, fontsize=7.5, ha="right")
ax.plot(x, pred, "-o", color=PRED, lw=2, ms=8, zorder=3,
        markeredgecolor=SURFACE, markeredgewidth=2, label="SPoSE prediction")
ax.errorbar(x, obs, yerr=err, fmt="-o", color=OBS, lw=2, ms=8, capsize=3,
            ecolor=OBS, elinewidth=1.4, zorder=4,
            markeredgecolor=SURFACE, markeredgewidth=2, label="adults observed")
for xi, o, (_, hi) in zip(x, obs, cis):
    ax.annotate(f"{o:.2f}", (xi, hi), textcoords="offset points", xytext=(0, 6),
                ha="center", fontsize=8, color=INK)
ax.set_xticks(x)
ax.set_xticklabels(["hardest\nquartile", "2nd", "3rd", "easiest\nquartile"])
ax.set_ylim(0.25, 1.06)
ax.set_ylabel("proportion correct")
ax.set_title("Adults track the predicted difficulty gradient — above it throughout",
             fontsize=9.5, loc="left", color=INK, pad=8)
ax.legend(frameon=False, loc="lower left", fontsize=8)
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# ---- B. RT across the same gradient ------------------------------------
ax = axes[0, 1]
rt = g.rt.median().values / 1000
ax.bar(x, rt, width=0.62, color=OBS, zorder=3)
for xi, v in zip(x, rt):
    ax.annotate(f"{v:.1f}s", (xi, v), textcoords="offset points", xytext=(0, 4),
                ha="center", fontsize=8, color=INK)
ax.set_xticks(x)
ax.set_xticklabels(["hardest\nquartile", "2nd", "3rd", "easiest\nquartile"])
ax.set_ylabel("median RT (s)")
ax.set_ylim(0, max(rt) * 1.22)
ax.set_title("…and slow down on the same items", fontsize=9.5, loc="left",
             color=INK, pad=8)
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# ---- C. accuracy across the session (fatigue check) --------------------
ax = axes[1, 0]
d2 = d.copy()
d2["chunk"] = np.minimum(d2.trial_index // 10, 6)
cg = d2.groupby("chunk")
xs = list(cg.groups.keys())
labels = [f"{k*10+1}-{k*10+10 if k < 6 else 71}" for k in xs]
acc = cg.correct.mean().values
band = np.array([wilson(int(gg.correct.sum()), len(gg)) for _, gg in cg])
ax.fill_between(xs, band[:, 0], band[:, 1], color=OBS, alpha=0.13, zorder=2)
ax.plot(xs, acc, "-o", color=OBS, lw=2, ms=7, zorder=3,
        markeredgecolor=SURFACE, markeredgewidth=2)
ax.axhline(1 / 3, color=GRID, lw=1, ls=(0, (4, 3)), zorder=1)
ax.set_xticks(xs)
ax.set_xticklabels(labels, fontsize=8)
ax.set_xlabel("trial number within the 71-trial session")
ax.set_ylabel("proportion correct")
ax.set_ylim(0.25, 1.06)
ax.set_title("No fatigue drift across the session", fontsize=9.5, loc="left",
             color=INK, pad=8)
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

# ---- D. bank coverage --------------------------------------------------
ax = axes[1, 1]
active = set()
for b in (manifest.get("adult_blocks") or [])[:meta["active_adult_blocks"]]:
    active.update(t["trial_id"] for t in b)
for key in ("intro", "core"):
    active.update(t["trial_id"] for t in manifest.get(key) or [])
counts = d.groupby("trial_id").size()
counts = counts[counts.index.isin(active)]
dist = pd.Series({k: int((counts == k).sum()) for k in range(1, int(counts.max()) + 1)})
dist.loc[0] = len(active) - len(counts)
dist = dist.sort_index()
ax.bar(dist.index, dist.values, width=0.62,
       color=[GRID if k == 0 else OBS for k in dist.index], zorder=3)
for k, v in dist.items():
    ax.annotate(str(v), (k, v), textcoords="offset points", xytext=(0, 4),
                ha="center", fontsize=8, color=INK)
ax.set_xticks(list(dist.index))
ax.set_xlabel("adults who have seen the item")
ax.set_ylabel("items in the active adult bank")
ax.set_ylim(0, dist.max() * 1.18)
ax.set_title(f"{len(counts)} of {len(active)} reachable items seen at least once",
             fontsize=9.5, loc="left", color=INK, pad=8)
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)

fig.text(0.055, 0.018,
         "Test trials only (training and catch excluded from panels A–B). "
         "Error bars / band are 95% Wilson intervals. "
         "Items are rotated: each adult sees intro + core + one 40-trial block.",
         fontsize=7.5, color=INK2)
fig.tight_layout(rect=[0.03, 0.045, 0.99, 0.955])
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, dpi=200)
print(f"wrote {OUT}")

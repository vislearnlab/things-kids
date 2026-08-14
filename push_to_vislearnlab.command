#!/bin/bash
# One-click push to vislearnlab/things-kids on GitHub.
# Requires: gh CLI (https://cli.github.com) and `gh auth login` done once.
# Double-click this file in Finder.

set -e
cd "$(dirname "$0")"

REPO="vislearnlab/things-kids"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh (GitHub CLI) is not installed."
  echo "Install with: brew install gh"
  echo "Then run: gh auth login"
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "You're not signed in to gh. Running 'gh auth login' now…"
  gh auth login
fi

# Make sure we're a git repo
if [ ! -d .git ]; then
  echo "Initializing git…"
  git init -b main
  git add .
  git -c user.email="cowork@local" -c user.name="Cowork" commit -m "Initial commit: THINGS Kids — Picture Detective"
fi

# Create the repo (if it doesn't already exist) and push
if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Repo $REPO already exists. Pushing latest commit."
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$REPO.git"
  git branch -M main
  git push -u origin main
else
  echo "Creating $REPO and pushing…"
  gh repo create "$REPO" --private --source=. --remote=origin --push \
    --description "Kid-friendly developmental version of the MOCHI 3D-shape oddity benchmark (jsPsych)."
fi

# Enable GitHub Pages with the workflow as the source
echo "Enabling GitHub Pages (build_type=workflow)…"
gh api -X POST "repos/$REPO/pages" \
  -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || echo "  (Pages may already be enabled — check Settings → Pages)"

echo
echo "✅ Done."
echo "Repo:   https://github.com/$REPO"
echo "Site:   https://vislearnlab.github.io/mochi-kids/  (allow ~30 s for first deploy)"
echo
echo "After the first push, the .github/workflows/pages.yml will publish public/ to Pages on every commit to main."
read -n 1 -s -r -p "Press any key to close…"

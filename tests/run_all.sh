#!/usr/bin/env bash
# Run every layer of tests. Exit non-zero on first failure.
# Used by .github/workflows/test.yml and `make test`.
set -e
cd "$(dirname "$0")/.."

echo "=== Layer 0: install + build ==="
echo "--> npm install (silent)"
npm install --silent
echo "    OK"

echo "--> Vite build"
npx vite build > /tmp/vite_build.log 2>&1
echo "    OK ($(grep '✓ built in' /tmp/vite_build.log | tail -1 || echo 'built'))"

echo
echo "=== Layer 1: static checks ==="
echo "--> TypeScript compile (server + experiment)"
npx tsc --noEmit
echo "    OK"

echo "--> Python compile (rendering + tests)"
python3 -m compileall -q rendering tests
echo "    OK"

echo "--> Asset integrity"
python3 tests/check_assets.py

echo
echo "=== Layer 2: end-to-end ==="
python3 tests/e2e_playthrough.py

echo
echo "--> Save/completion ordering (adult + Prolific redirect)"
python3 tests/save_completion_check.py

echo
echo "--> Debrief comment reaches the payload"
python3 tests/debrief_comment_check.py

echo
echo "=== ALL TESTS PASSED ==="

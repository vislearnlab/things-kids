#!/bin/bash
# Double-click in Finder to start the dev server.
# Runs `npm install` first time, then `npm run dev`. Cmd+C in the
# Terminal window to stop.

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if ! command -v node >/dev/null 2>&1; then
  echo "Error: Node.js not installed. Install from https://nodejs.org or run 'brew install node'."
  read -n 1 -s -r -p "Press any key to close…"
  exit 1
fi

if [ ! -d node_modules ]; then
  echo "First run — installing dependencies (this may take a minute)…"
  npm install
fi

echo
echo "Starting dev server (will open browser automatically)."
echo "Cmd+C in this window when you're done."
echo
( sleep 2 && open "http://localhost:3000/?save=false" ) &
npm run dev

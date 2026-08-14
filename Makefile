.PHONY: install dev build serve start prod test test-static test-e2e sanity clean

install:
	npm install

# Frontend dev server with hot reload (Vite). Doesn't save data anywhere.
dev:
	npm run dev

# Build the static frontend (Vite -> dist/).
build:
	npm run build

# Same as dev — kept for back-compat with start.command.
serve: dev

# Run the Express + MongoDB server (after `npm run build`).
# Reads MONGO_URL etc. from .env.
start:
	npm run start

# Build + run the server (production).
prod:
	npm run prod

# Full test suite (matches CI).
test:
	bash tests/run_all.sh

test-static:
	python3 tests/check_assets.py

test-e2e:
	python3 tests/e2e_playthrough.py

# Pull data from Mongo and knit the sanity-check Rmd. Opens the HTML on macOS.
sanity:
	python3 analysis/fetch_data.py
	Rscript -e 'rmarkdown::render("analysis/sanity_check.Rmd")'
	@command -v open >/dev/null 2>&1 && open analysis/sanity_check.html || true

clean:
	rm -rf dist dist-server node_modules
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf rendering/meshes rendering/rotation_frames

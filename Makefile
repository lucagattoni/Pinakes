# pinakes — task runner.
#
# Every target wraps the command CI actually runs (.github/workflows/ci.yml, and docs.yml for the
# two docs targets), so a green `make check` locally means the same thing it means on the runner.
# `--frozen` everywhere: the lockfile is the contract, and a target that silently re-resolves it
# would hide the drift CI would catch.
#
# `check` is the gate; check.sh remains its shell entrypoint (git hooks and docs reference it).

.DEFAULT_GOAL := help
SHELL := /bin/sh
DEMO_KB := tests/demo-kb
# mkdocs is deliberately not a project dependency — it would pull a docs toolchain into the
# environment `check` and the release wheel resolve. `--no-project` runs it from an ephemeral one.
DOCS := uv run --no-project --with-requirements requirements-docs.txt mkdocs

.PHONY: help install check fmt fmt-check lint types types-fast test test-model eval demo doctor \
        budget corpus pdf-eval build smoke clean release-check docs docs-serve

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the dev environment (light extra — CI's minimum leg; add --extra pdf/claude for the others)
	uv sync --frozen --extra light

check:  ## Every gate, stopping at the first failure — run before every commit
	./check.sh

fmt:  ## Reformat (covers Python blocks inside Markdown — that is not a typo)
	uv run --frozen ruff format .

fmt-check:  ## Formatting gate only
	uv run --frozen ruff format --check .

lint:  ## Lint gate only
	uv run --frozen ruff check .

types-fast:  ## ty — fast pre-check, never the gate (docs/RETROSPECTIVES.md, I1)
	uv run --frozen ty check --extra-search-path stubs .

types:  ## pyright strict — the type gate
	uv run --frozen pyright

test:  ## Unit tests (model-backed tests excluded)
	uv run --frozen pytest -q

test-model:  ## Model-backed tests — downloads weights to HF_HOME on first run
	uv run --frozen pytest -q -m model

demo:  ## Index the synthetic demo KB
	uv run --frozen pnk sync --kb $(DEMO_KB)

doctor:  ## Health-check the demo KB
	uv run --frozen pnk doctor --kb $(DEMO_KB)

budget:  ## Show the demo KB's spend ledger (free: it only reads)
	uv run --frozen pnk budget --kb $(DEMO_KB)

eval:  ## Golden-set evaluation against the baseline (needs `make demo` first)
	uv run --frozen python -m pinakes.eval $(DEMO_KB)

corpus:  ## Regenerate tests/pdf-corpus/ in place — review with `git diff` before committing
	SOURCE_DATE_EPOCH=1785181219 uv run --frozen python3 tests/pdf-corpus/generate.py

pdf-eval:  ## Extraction-quality baseline + floor-drift check against tests/pdf-corpus (needs [pdf])
	uv run --frozen python -m pinakes.extract.quality tests/pdf-corpus \
		--check-floors src/pinakes/extract/floors.toml

build:  ## Build wheel and sdist
	uv build

smoke: build  ## Install the built wheel in isolation and run it — what release does
	uv run --isolated --no-project --with dist/*.whl pnk --version

release-check:  ## Verify the git tag you are about to push matches pinakes.__version__
	@version="$$(uv run --frozen python -c 'import pinakes; print(pinakes.__version__)')"; \
	echo "package version: $$version"; \
	echo "tag to push:     v$$version"; \
	echo "publishing is manual by design: git tag -a v$$version -m ... && git push origin v$$version"

docs:  ## Build the docs site into site/ — --strict, exactly what the docs workflow runs
	$(DOCS) build --strict

docs-serve:  ## Preview the docs site at http://127.0.0.1:8000 with live reload
	$(DOCS) serve

clean:  ## Remove build artifacts and caches (never touches .pinakes/ or the lockfile)
	rm -rf dist build site .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

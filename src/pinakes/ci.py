"""`pnk init --ci` — the GitHub Actions workflow that keeps a published KB fresh (§6.3, I6b).

DESIGN §6.3 designed this in v0.1 and v0.1 never built it, so I6b builds it here — in the increment
that needs it to force the free backend, because writing a modification to an unbuilt writer is the
same defect as writing a hook around an unbuilt flag.

**The workflow forces `--extract=pypdfium2`, exactly as the git hooks do** (`hooks.py`'s docstring
carries the full reasoning). A CI job is the most non-interactive caller there is: it has no
terminal to answer a `confirm_above_eur` prompt from, and no CI job in this project ever holds an
API key. Sharing `hooks.FREE_BACKEND_FLAG` rather than repeating the string is deliberate — two
literals are two places for the forced backend to drift.

The cache key is keyed on the sources, so a run that changes nothing restores `.pinakes/` and syncs
nothing. `ledger.jsonl` lives in that same directory and is restored with it; CI cannot spend, so
it cannot add to it either.
"""

from pathlib import Path

from pinakes.errors import InitError
from pinakes.hooks import FREE_BACKEND_FLAG

WORKFLOW_PATH = Path(".github") / "workflows" / "pinakes.yml"

_CACHE_KEY = "pinakes-${{ runner.os }}-${{ hashFiles('docs/**', 'pinakes.toml') }}"

WORKFLOW = f"""\
# Installed by `pnk init --ci`. Keeps the index fresh for a published KB.
#
# This workflow runs `pnk sync {FREE_BACKEND_FLAG}`: CI is non-interactive and must never spend.
# Paid extraction stays a deliberate `pnk sync` a human runs.
name: pinakes

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5

      - name: Restore the index
        uses: actions/cache@v4
        with:
          path: .pinakes
          key: {_CACHE_KEY}
          restore-keys: pinakes-${{{{ runner.os }}}}-

      - name: Sync
        run: uvx --from 'pinakes[light,pdf]' pnk sync {FREE_BACKEND_FLAG}

      - name: Health check
        run: uvx --from 'pinakes[light,pdf]' pnk doctor
"""


def write_workflow(root: Path) -> Path:
    """Write the workflow into `root`, refusing to overwrite an existing one.

    An existing workflow may be hand-edited — the same trust rule `install-hooks` applies to a
    foreign git hook, for the same reason.
    """
    path = root / WORKFLOW_PATH
    if path.exists():
        raise InitError(
            f"{path} already exists.",
            remedy="Delete it first if you want the generated workflow; it is never overwritten.",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(WORKFLOW, encoding="utf-8")
    return path

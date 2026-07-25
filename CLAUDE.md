# pinakes — project instructions

Architecture lives in [`docs/DESIGN.md`](docs/DESIGN.md). It is the source of truth; this file only
carries rules that change how you work.

## This repository is PUBLIC

- **Never commit real knowledge-base content.** The repo is the engine. The only KB here is the
  synthetic demo corpus under `tests/` — written for the purpose, never harvested.
- Vet every file for PII, credentials, private URLs, and anything copied from memory before staging.
- Never commit model weights or `.pinakes/` state (both are gitignored — keep it that way).

## Naming (fixed — changing any of these is a breaking change)

| Thing | Value |
|---|---|
| Package / command | `pinakes` / `pnk` |
| Manifest / sidecar | `pinakes.toml` / `<file>.pnk.yaml` |
| Generated state | `.pinakes/` |
| MCP tools | `pinakes_*` — never bare `kb_*`, which collides across servers |
| Cross-KB URI | `pnk://<kb-ulid>/<doc-ulid>` — ULIDs only, never aliases |

## Invariants that must not be broken

- **Document and KB ULIDs are permanent.** Never renumber, never regenerate. Every inbound link
  depends on them, and there is no migration machinery by design.
- **`docs/` belongs to the user.** Never modify source documents, and never delete a sidecar without
  an explicit `--prune`-style flag plus a printed list.
- **`.pinakes/` is disposable except `ledger.jsonl`** — a rebuild must preserve spend history.
- **The free path stays free.** No code path may make a paid API call outside `pnk ask --deep`.
- Index schema changes bump `schema_version` and require a rebuild. Never write a migration.

## Tooling

- **uv only** — `uv add`, `uv run`, `uv build`. Never pip, poetry, or a hand-managed venv.
- Python 3.13+. `ruff`, `pyright` (strict), `pytest` must pass before any commit.
- **Core dependencies stay light.** Nothing pulling torch enters `[project.dependencies]` —
  embedding backends are extras (`[st]`, `[light]`). CI runs `[light]`.

## Changing retrieval

Any change to chunking, fusion weights, reranking or the confidence signal must be justified by the
golden-set eval (`recall@k`, MRR, false-abstain rate) — never by intuition alone. Report the before
and after numbers in the commit message.

## Docs

A change to any user-facing surface (CLI flag, manifest key, MCP tool, default, behaviour) updates
`docs/DESIGN.md`, the README and `--help` text **in the same commit**.

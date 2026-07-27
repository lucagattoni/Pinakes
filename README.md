# pinakes

**A portable, agent-first knowledge base. One directory = one KB.**

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)

> **Status: v0.1 — the vertical slice works.** `init`, `sync`, `search`, `doctor`, `install-hooks`
> and `serve` are implemented and tested. The architecture is specified in
> [`docs/DESIGN.md`](docs/DESIGN.md) (seven adversarial review passes) and was built increment by
> increment against [`plans/v0.1.md`](plans/v0.1.md), with a retrospective after each
> ([`docs/RETROSPECTIVES.md`](docs/RETROSPECTIVES.md)).

---

## The idea

A knowledge base is a plain directory you can read, edit, diff, commit and hand to someone:

```
my-kb/
├── pinakes.toml              # manifest: sources, models, chunking, budget
├── docs/                     # SOURCE OF TRUTH — your files, unmodified
│   ├── paper.md
│   └── paper.md.pnk.yaml     # sidecar: stable ID, tags, links, provenance
└── .pinakes/                 # generated, disposable, gitignored
    └── index.db              # SQLite: chunks, FTS5, vectors, links
```

Your documents and their metadata are the truth. The index is derived state that can always be
rebuilt. That split is what makes a KB both a **reproducible recipe** and a directory you can move.

## What makes it different

**It costs nothing to run.** Retrieval is BM25 (SQLite FTS5) + local embeddings + local reranking,
fused and scored entirely on your CPU. No API key is needed to search, and re-indexing is free — so
there is never a cost reason not to improve your chunking or swap your embedding model.

**Reasoning is the caller's, not the KB's.** The MCP tools return ranked, cited evidence.
`pinakes_search → pinakes_get → pinakes_search` *is* a plan-retrieve-read-refine loop, and your agent
already runs it in its own context. Multi-hop reasoning falls out of composable tools rather than a
second agent framework. A `pnk ask --deep` path is **planned for v0.4** for CLI and cron use, where no
agent is present — that one will spend money, and is the only thing the budget system will guard.

**Spending will be bounded, not merely observed** (v0.4, with the first paid path). Pre-call
reservation makes a hard cap a real ceiling rather than an after-the-fact report, and a rolling
ledger tracks daily and monthly spend. The manifest's `[budget]` block is already parsed and
validated so a KB authored today stays valid then; nothing consumes it yet.

**KBs link to each other.** Sidecars carry `pnk://<kb-ulid>/<doc-ulid>` references, so links survive
renames, moves, and being shared with someone else.

## Usage

**Not yet on PyPI** — trusted publishing is still to be configured — so install from source:

```bash
uv add "pinakes[st] @ git+https://github.com/lucagattoni/Pinakes"     # default backend
uv add "pinakes[light] @ git+https://github.com/lucagattoni/Pinakes"  # fastembed, no torch
```

```bash
pnk init my-kb                        # stamp a KB (--template notes is the default)
pnk sync                              # index what changed (git-hook friendly)
pnk search "hybrid retrieval"         # free: BM25 + vector + rerank, with a
                                      # confidence signal that says `unknown` until calibrated
pnk doctor                            # environment, coherence, orphans, link coverage

uvx --from "git+https://github.com/lucagattoni/Pinakes" pnk serve     # MCP server
```

Once published, the install lines shorten to `uv add "pinakes[st]"` (sentence-transformers — widest
model choice, pulls torch) or `uv add "pinakes[light]"` (fastembed — ONNX, ~100MB, no torch).

`pnk init` stamps the sentence-transformers backend by default. **On a `[light]` install, set
`provider = "fastembed"` under `[embedding]` in `pinakes.toml` before your first `pnk sync`** —
otherwise sync stops with "the sentence-transformers backend is not installed", which is an accurate
message for an avoidable wall.

## Development

```bash
make install    # sync the dev environment (the light extra, as CI does)
make check      # every gate, stopping at the first failure — run before every commit
make demo       # index the synthetic demo KB
make eval       # golden-set evaluation against the recorded baseline
make help       # all targets
```

Every target wraps the command CI actually runs, so green locally means green on the runner. Note
that `make check` formats Python **inside Markdown fences** too — a docs-only change can fail it.

## Design

[`docs/DESIGN.md`](docs/DESIGN.md) is the specification: storage schema, sync semantics, concurrency
policy, budget accounting, cross-KB linking, and the delivery plan. It also documents its own review
history — seven passes, 58 findings, including four externally verified claims, two of which the
review found to be false.

[`docs/graph/`](docs/graph/) holds the graph-retrieval research that shapes v0.3 — fourteen
investigations of the GraphRAG-family projects and
[`PINAKES_APPROACH.md`](docs/graph/PINAKES_APPROACH.md), which turns them into a gated build order.

Three limits are stated there rather than hidden: no vector tier is sublinear (`sqlite-vec` performs
exhaustive KNN, not approximate search); without fan-out query, cross-KB answers are capped by how
well your KBs are linked; and the confidence signal is a calibrated heuristic whose measured
false-confidence rate on the demo corpus is **0.25** — one no-answer question in four still gets a
confident answer. That number is published because a heuristic whose cost is unmeasured is worse
than one whose cost is known.

## Your data stays yours

This repository contains the **engine only**. Real knowledge bases live outside it. The sole KB in
this repo is a small synthetic corpus used for tests and retrieval benchmarking.

`pnk init` ships a `.gitignore` covering `.pinakes/`, so your index — and, from v0.4, your spend
ledger — never leaves your machine. Note that publishing a KB repo publishes `docs/` *and* every sidecar — titles, tags and
provenance URLs included.

## Licence

[Apache-2.0](LICENSE).

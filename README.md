# pinakes

**A portable, agent-first knowledge base. One directory = one KB.**

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)

> **Status: design complete, implementation not started.** Nothing here works yet. The architecture
> is specified in [`docs/DESIGN.md`](docs/DESIGN.md) and has been through six adversarial review
> passes. There is no PyPI release; the install instructions below describe the intended v0.1.

---

## The idea

A knowledge base is a plain directory you can read, edit, diff, commit and hand to someone:

```
my-kb/
├── pinakes.toml              # manifest: sources, models, chunking, budget
├── docs/                     # SOURCE OF TRUTH — your files, unmodified
│   ├── paper.pdf
│   └── paper.pdf.pnk.yaml    # sidecar: stable ID, tags, links, provenance
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
second agent framework. A `pnk ask --deep` path exists for CLI and cron use, where no agent is
present — that one spends money, and is the only thing the budget system guards.

**Spending is bounded, not merely observed.** Pre-call reservation means a hard cap is a real
ceiling rather than an after-the-fact report; a rolling ledger tracks daily and monthly spend.

**KBs link to each other.** Sidecars carry `pnk://<kb-ulid>/<doc-ulid>` references, so links survive
renames, moves, and being shared with someone else.

## Intended usage (v0.1)

```bash
uv add "pinakes[st]"                  # sentence-transformers backend (default)
uv add "pinakes[light]"               # fastembed — ONNX, ~100MB, no torch

pnk init my-kb --template notes       # stamp a KB from a blueprint
pnk sync                              # index what changed (git-hook friendly)
pnk search "hybrid retrieval"         # free: BM25 + vector + rerank
pnk doctor                            # environment, coherence, orphans, link coverage

uvx --from "pinakes[st]" pnk serve    # MCP server, zero install
```

## Design

[`docs/DESIGN.md`](docs/DESIGN.md) is the specification: storage schema, sync semantics, concurrency
policy, budget accounting, cross-KB linking, and the delivery plan. It also documents its own review
history — six passes, 54 findings, including the three factual errors the review caught.

Two limits are stated there rather than hidden: no vector tier is sublinear (`sqlite-vec` performs
exhaustive KNN, not approximate search), and without fan-out query, cross-KB answers are capped by
how well your KBs are linked.

## Your data stays yours

This repository contains the **engine only**. Real knowledge bases live outside it. The sole KB in
this repo is a small synthetic corpus used for tests and retrieval benchmarking.

`pnk init` ships a `.gitignore` covering `.pinakes/`, so your index and spend ledger never leave your
machine. Note that publishing a KB repo publishes `docs/` *and* every sidecar — titles, tags and
provenance URLs included.

## Licence

[Apache-2.0](LICENSE).

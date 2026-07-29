# pinakes

**A portable, agent-first knowledge base. One directory = one KB.**

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

[![PyPI](https://img.shields.io/pypi/v/pinakes.svg)](https://pypi.org/project/pinakes/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/)

📖 **[Guide](docs/GUIDE.md)** · **[CLI](docs/CLI.md)** · **[Manifest](docs/MANIFEST.md)** ·
**[Design](docs/DESIGN.md)** · **[What ships today](docs/STATUS.md)**

---

## The idea

A knowledge base is a plain directory you can read, edit, diff, commit and hand to someone:

```
my-kb/
├── pinakes.toml              # manifest: sources, models, chunking, budget
├── docs/                     # SOURCE OF TRUTH — your files, unmodified
│   ├── paper.pdf
│   ├── paper.pdf.pnk.yaml    # sidecar: stable ID, tags, links, provenance
│   ├── notes.md
│   └── notes.md.pnk.yaml
└── .pinakes/                 # generated, disposable, gitignored
    └── index.db              # SQLite: chunks, FTS5, vectors, links
```

Your documents and their metadata are the truth. The index is derived state that can always be
rebuilt. That split is what makes a KB both a **reproducible recipe** and a directory you can move.

## What makes it different

**It costs nothing to run.** Retrieval is BM25 (SQLite FTS5) + local embeddings + local reranking,
fused and scored entirely on your CPU. No API key is needed to search, and re-indexing is free — so
there is never a cost reason not to improve your chunking or swap your embedding model. That the
free path stays free is enforced by a CI gate, not by a promise.

**Reasoning is the caller's, not the KB's.** The MCP tools return ranked, cited evidence.
`pinakes_search → pinakes_get → pinakes_search` *is* a plan-retrieve-read-refine loop, and your agent
already runs it in its own context. Multi-hop reasoning falls out of composable tools rather than a
second agent framework.

**Money is opt-in and bounded by design.** Every paid path is an explicit, enumerated entry point,
and a pre-call reservation makes a hard cap a real ceiling rather than an after-the-fact report.
See [what is actually built](docs/STATUS.md).

**KBs link to each other.** Sidecars carry `pnk://<kb-ulid>/<doc-ulid>` references, so links survive
renames, moves, and being shared with someone else. The *addressing* ships today because IDs cannot
be retrofitted; authoring and traversing those links is [the links
release](docs/STATUS.md#release-roadmap).

**Its limits are published, not hidden.** No vector tier is sublinear; cross-KB answers will be
capped by how well your KBs are linked; and the confidence heuristic's measured false-confidence rate is
**0.25** — one no-answer question in four still gets a confident answer. A heuristic whose cost is
unmeasured is worse than one whose cost is known.

## Quickstart

```bash
uv add "pinakes[st]"                  # default backend
uv add "pinakes[light]"               # fastembed, no torch
uv add "pinakes[light,pdf]"           # + PDF ingest, free and local
uv add "pinakes[light,pdf,claude]"    # + the opt-in paid extractor for scanned PDFs
```

`[claude]` installs a path that can spend money, and nothing spends without you asking: the default
extractor is free, and reaching the paid one takes `--extract=claude-vision` (or a manifest key)
**and** a real API key in the environment. When you do ask, the run is priced before the first call
and refused if it would breach any of the three `[budget]` caps — `per_operation_eur`, `daily_eur`
or `monthly_eur`. Raising one and hitting the next is the discovery path those caps exist to
prevent, so a refusal names every window that binds, not just the first. `pnk budget` reports what
has been spent.

```bash
pnk init my-kb                        # stamp a KB
pnk sync                              # index what changed (git-hook friendly)
pnk search "hybrid retrieval"         # free: BM25 + vector + rerank
pnk doctor                            # environment, coherence, orphans, link coverage

uvx --from "pinakes[st]" pnk serve    # MCP server, nothing installed
```

⚠️ Two things `pnk init` cannot know, each needing one manifest edit: on a `[light]` install set
`provider = "fastembed"`, and to index PDFs add `"**/*.pdf"` to `[sources] include`. Both are in the
[Guide](docs/GUIDE.md#choosing-a-backend).

**→ [Full guide](docs/GUIDE.md)** — PDFs, filters, calibration, git hooks, MCP setup, troubleshooting.

## Development

```bash
make install    # sync the dev environment (the light extra — CI's minimum leg)
make check      # every gate, stopping at the first failure — run before every commit
make demo       # index the synthetic demo KB
make eval       # golden-set evaluation against the recorded baseline
make corpus     # regenerate the synthetic PDF corpus in place
make pdf-eval   # extraction-quality baseline + floor-drift check (needs [pdf])
make budget     # the demo KB's spend ledger (free: it only reads)
make help       # all targets
```

Every target wraps the command CI actually runs, so green locally means green on the runner. Note
that `make check` formats Python **inside Markdown fences** too — a docs-only change can fail it.

Conventions and the increment workflow are in [`CLAUDE.md`](CLAUDE.md); how the docs are organised —
and which file to edit when you land a feature — is in [`docs/README.md`](docs/README.md).
[`docs/VERIFICATION.md`](docs/VERIFICATION.md) maps every promise this project makes to the test
that holds it, and a test asserts every one of those tests exists.

## Your data stays yours

This repository contains the **engine only**. Real knowledge bases live outside it. The sole KB here
is a small synthetic corpus used for tests and retrieval benchmarking, and the only other committed
content is `tests/pdf-corpus/` — PDFs generated from scratch by a committed script to exercise hard
extraction cases. Neither was harvested from anywhere; no real-world document is committed here.

`pnk init` ships a `.gitignore` covering `.pinakes/`, so your index — and your spend ledger — never
leaves your machine. Note that publishing a KB repo publishes `docs/` *and* every sidecar: titles,
tags and provenance URLs included.

## Licence

[Apache-2.0](LICENSE).

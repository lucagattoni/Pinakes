# pinakes documentation

**A portable, agent-first knowledge base. One directory = one KB.**

Your documents and their sidecars are the source of truth; the index is derived state that can
always be rebuilt. Retrieval — BM25, local embeddings, local reranking — runs entirely on your
CPU and costs nothing, and a CI gate holds that promise rather than a sentence in a README.

> *The* Pinakes *were Callimachus's catalogue of the Library of Alexandria — the first known index
> of a body of knowledge.*

This documentation is ordered **simple → deep**: start with the Guide, go deeper as you need.

<div class="grid cards" markdown>

- :material-rocket-launch-outline:{ .lg .middle } **Guide**

    ---

    Install, stamp your first KB, index PDFs, search, keep the index fresh, wire it into an agent
    over MCP, and troubleshoot. No prior knowledge assumed.

    [:octicons-arrow-right-24: Guide](GUIDE.md)

- :material-tune:{ .lg .middle } **Reference**

    ---

    Every command and flag with its exit codes, every `pinakes.toml` and sidecar field with its
    default, and the table mapping each promise this project makes to the test that holds it.

    [:octicons-arrow-right-24: CLI](CLI.md) ·
    [Manifest](MANIFEST.md) ·
    [Verification](VERIFICATION.md)

- :material-graph-outline:{ .lg .middle } **Concepts**

    ---

    Why it is built this way: KB anatomy, storage, the retrieval pipeline, cost control, sync
    semantics and concurrency — with the trade-offs named, not hidden.

    [:octicons-arrow-right-24: Design](DESIGN.md) ·
    [Updating an existing KB](KB-UPDATES.md)

- :material-progress-check:{ .lg .middle } **Project**

    ---

    What actually ships today, the measured numbers and when they were measured, the paid
    measurement runbook, the release procedure, and what every increment taught us.

    [:octicons-arrow-right-24: Status](STATUS.md) ·
    [Measurement run](MEASUREMENT-RUN.md) ·
    [Releasing](RELEASING.md) ·
    [Retrospectives](RETROSPECTIVES.md)

- :material-book-search-outline:{ .lg .middle } **Graph research**

    ---

    Thirteen investigations — twelve external projects plus the in-house precedent — and the
    synthesis that turned them into a gated build order. Research, not specification: where it
    disagrees with Design, Design wins.

    [:octicons-arrow-right-24: Overview](graph/README.md) ·
    [The pinakes approach](graph/PINAKES_APPROACH.md)

</div>

## Quickstart

```bash
uv add "pinakes[st]"                  # default backend
uv add "pinakes[light]"               # fastembed, no torch

pnk init my-kb                        # stamp a KB
pnk sync                              # index what changed (git-hook friendly)
pnk search "hybrid retrieval"         # free: BM25 + vector + rerank
pnk doctor                            # environment, coherence, orphans, link coverage
```

!!! warning "Two things `pnk init` cannot know"

    Each needs one manifest edit: on a `[light]` install set `provider = "fastembed"`, and to
    index PDFs add `"**/*.pdf"` to `[sources] include`. Both are in
    [the Guide](GUIDE.md#choosing-a-backend).

## Reading paths

**New here?**
[Guide § Install](GUIDE.md#install) →
[Your first KB](GUIDE.md#your-first-kb) →
[Searching](GUIDE.md#searching) →
[CLI reference](CLI.md).

**Wiring it into an agent?**
[Guide § Using it from an agent](GUIDE.md#using-it-from-an-agent) →
[`pnk serve`](CLI.md#pnk-serve) →
[Design § Retrieval](DESIGN.md#4-retrieval).

**Evaluating the design?**
[Design](DESIGN.md) →
[Status § Measured numbers](STATUS.md#measured-numbers) →
[Verification](VERIFICATION.md) →
[Graph research](graph/PINAKES_APPROACH.md).

**Spending money on scanned PDFs?**
[Guide § Indexing PDFs](GUIDE.md#indexing-pdfs) →
[Design § Cost control](DESIGN.md#5-cost-control) →
[The measurement run](MEASUREMENT-RUN.md).

## What is true, and where it is written

**One fact, one home.** Every claim below lives in exactly one file; everywhere else links to it.
This page is deliberately **version-free** — it says what pinakes *is*, never which release you are
on, so it does not go stale.

| Question | Answer lives in |
|---|---|
| Does this exist yet? | [Status](STATUS.md) — the only file in the repo that says what is built |
| What does this flag do? | [CLI](CLI.md); `--help` is authoritative, CLI adds when and why |
| What goes in `pinakes.toml`? | [Manifest and sidecar](MANIFEST.md) |
| How do I accomplish a task? | [Guide](GUIDE.md) |
| Why is it built this way? | [Design](DESIGN.md) |
| What holds this promise? | [Verification](VERIFICATION.md) — and a test asserts each named test exists |
| What did we learn? | [Retrospectives](RETROSPECTIVES.md) |

## Elsewhere in the repo

- [Changelog](https://github.com/lucagattoni/Pinakes/blob/main/CHANGELOG.md) —
  versioned release history
- [Build plans](https://github.com/lucagattoni/Pinakes/tree/main/plans) —
  the current build order, decision records and iteration logs
- [Docs routing table](https://github.com/lucagattoni/Pinakes/blob/main/docs/README.md) —
  which file to edit when an increment lands
- [`CLAUDE.md`](https://github.com/lucagattoni/Pinakes/blob/main/CLAUDE.md) —
  the conventions and invariants an agent working here must follow

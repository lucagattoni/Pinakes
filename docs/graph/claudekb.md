# ClaudeKB — the in-house precedent

**Repo:** local (github_lucagattoni/ClaudeKB) · **Investigated:** 20260725 15:31

## What it is

ClaudeKB is not a knowledge base — it is a **blueprint**: a copier template plus a small Python
toolchain (`kbtool`, ~1,150 lines across 11 modules in `src/kbtool/`) that scaffolds and upgrades a
fleet of independent KB repos. Each generated KB is a standalone git repo of Markdown under
`docs/`, validated by a strict gate (`kbtool check`), built by a static site generator (Zensical,
with an mkdocs-material fallback), and deployed as a private-by-default static site behind
Cloudflare Access. Agents write to it by **direct commits to main**; Workers Builds re-runs the
gate on push and deploys only if green. The KB never depends on the blueprint at runtime — kbtool
travels inside each KB as a vendored wheel, playbooks ship as package data, and a checksum manifest
(`blueprint-checksums.json`) enforces the blueprint-owned vs KB-owned file boundary.

Reached v0.4.0 in a single day of adversarial-review-driven design (9 review passes recorded in
`docs/architecture.md`'s iteration log); KB #1 went live end-to-end and drove two post-launch fixes.

## How knowledge is structured

- **Pages**: long-form Markdown under `docs/`, one concept per page. Required frontmatter on every
  page (`type`, `title`, `description`), validated against a JSON Schema plus a per-KB controlled
  vocabulary (`vocab.yml` lists allowed `type`s and `tags`). `index.md`/`log.md` are frontmatter-free
  by convention (Open Knowledge Format alignment). No date fields — dates derive from git history.
- **Links are plain Markdown and human/agent-authored**: intra-KB bundle-root-absolute
  (`[X](/concepts/alpha.md)`); cross-KB via a logical scheme `kb://<kb-name>/<path>.md`, rewritten
  at build time to a real URL (`https://kb-<name>.<domain>/<url-path>`). One shared implementation
  (`src/kbtool/links.py`) serves both the validator and the preprocessor.
- **Graph-ness is enforced, not just permitted.** Two structural validators make the corpus a
  connected graph by construction (`src/kbtool/validators.py`):
  - `check_index_reachability` — every page must be reachable from `docs/index.md` by following
    intra-KB links (BFS over the link graph). Orphans are build **errors**.
  - `check_nav` — every page must appear in the curated `nav.yml` (explicitly or via a glob
    section). Missing-from-nav is an error.
  So there is a real link graph, but no backlinks, no typed edges, no graph queries — a
  "backlinks emitter" derived from the validator's link graph is explicitly deferred
  (`docs/guide/roadmap.md`).
- **Catalog and log**: `docs/index.md` is a hand-curated catalog (the graph's root); `docs/log.md`
  is an append-only change log with a git union-merge driver so parallel agent sessions both land.

## How retrieval actually happens

There is **no retrieval engine**. Three mechanisms, none ranked:

1. **The agent reads files.** The session ritual (`template/CLAUDE.md`) starts every session with
   "read `docs/index.md` and the tail of `docs/log.md`" — the catalog is the entry point, then the
   agent navigates links or greps. Retrieval quality is entirely the agent's navigation plus the
   curator's discipline in keeping `index.md` honest.
2. **Client-side site search** for human readers: the SSG emits a `search.json` lexical index
   (kept behind the login on private KBs). Nothing consumes it programmatically.
3. **Structure as recall insurance**: the orphan check guarantees anything ingested is findable by
   walking from the index — retrieval-by-navigation cannot silently lose a page.

Cross-KB search, an MCP/RAG layer, and backlinks are all named as "future extensions (designed
for, not built)" — the design's stated bet is that plain Markdown in git is "directly ingestible
by future retrieval layers" (`README.md`, `docs/guide/what-is-claudekb.md`).

## The agent's role: Claude as the engine

ClaudeKB inverts Pinakes' architecture. Pinakes is an engine Claude calls as tools; ClaudeKB is
**Claude as the engine over plain files**, with code confined to validation and plumbing:

- All intelligence — deciding create-vs-extend, writing, linking, curating the index, semantic
  maintenance — is delegated to the agent via *prose contracts*: a checksummed, blueprint-owned
  `CLAUDE.md` (session ritual, conventions) plus a KB-owned `CLAUDE-KB.md` (topic, page types),
  and versioned playbooks printed by `kbtool playbook <ingest|lint|upgrade|access-dns-setup>`.
- Code never touches meaning; it enforces *shape*: schema, link resolution, reachability, nav
  coverage, append-only log, ownership checksums, secret scan, Markdown lint.
- Where the agent can't be trusted, the design uses **structural guarantees over conventions**
  (the blueprint CLAUDE.md's first working principle): the deploy gate re-runs everything in CI, so
  a contract-violating commit lands in git but never deploys.
- Even corpus health is an agent job: the `lint` playbook is a scheduled agent session doing a
  semantic pass — contradictions, staleness, "orphan-in-spirit" pages, missing cross-references.

## Guardrails and publishing

- **Two independent visibility axes** (`docs/guide/public-and-private-kbs.md`): repo visibility
  (GitHub — exposes source, full history, commit emails) vs site visibility (Cloudflare Access —
  exposes rendered content). The guide enumerates all four combinations and their exposures.
- **Secret scan in the gate** (v0.4.0, `src/kbtool/secrets.py`): scans `docs/**/*.md` for
  private-key blocks and provider token shapes (AWS/GitHub/Google/Slack). High-confidence match =
  **error on a public KB** (deploy blocked), **warning on a private one** — so you learn before
  ever flipping it public. Personal emails and generic `key = <long value>` assignments are always
  warnings; example/noreply addresses are ignored; `kbtool-allow-secret` on a line suppresses.
- **Publish-safe identity**: the scaffold sets the KB's git email to a GitHub noreply so history is
  safe if the repo ever goes public; the publish checklist demands vetting *history*, not just the
  tree.
- **Partial-public split**: only `docs/public/**` is world-readable on a private site; documented
  residual leaks (global nav exposes private page *titles*; `kb://` links to private KBs reveal
  their existence and paths) are accepted and written down rather than hidden.
- **`kbtool verify-access`** probes the live site anonymously and asserts behaviour matches the
  `kb.yml` record — repo as source of truth, dashboard as cache.

## ClaudeKB vs Pinakes, dimension by dimension

| Dimension | ClaudeKB | Pinakes |
|---|---|---|
| Source of truth | Markdown + frontmatter in git, per-KB repo | Source docs + `.pnk.yaml` sidecars in git |
| Index | None (SSG `search.json` for humans only) | SQLite (`.pinakes/index.db`), disposable, rebuilt free |
| Retrieval | Agent navigation from a curated index + grep | BM25 + local embeddings + RRF + rerank + confidence |
| Linking/graph | Untyped Markdown links; reachability + nav enforced; `kb://` cross-KB | Typed sidecar links (`rel: cites`), `pnk://` ULIDs; free structural edges planned |
| Link stability | Path-based — a rename breaks inbound links (redirects `_redirects` for URL moves) | ULIDs permanent by invariant; paths can churn |
| Multi-hop | Agent follows links across reads | Caller's agent composes `pinakes_*` tools |
| Cost model | Free infra (Cloudflare free tier); "cost" is agent tokens per read/write session | Free path sacred; paid only in explicit `pnk ask --deep` |
| Portability | Very high — any SSG, any Markdown consumer; SSG-independent by design | High for content; index/rerank need Python + models |
| Agent role | The engine: writes, curates, retrieves, maintains | A client: calls tools; engine ranks and abstains |
| Publishing | First-class: build → deploy → Access gating, public subtree | Out of scope (engine only, repo public but KBs private) |
| Consistency enforcement | Deploy gate re-runs all validators in CI | Local checks; index rebuild tolerant |

The deepest difference: **where recall lives**. ClaudeKB buys recall structurally at *write* time
(nothing may exist unlinked, vocab is controlled, the index page is curated every session) and
spends agent tokens at *read* time. Pinakes buys recall computationally at read time (lexical +
semantic + rerank) and lets write-time metadata be sparse. ClaudeKB's retrieval degrades with
corpus size and agent context limits; Pinakes' degrades with index staleness and model quality.

## What ClaudeKB does better or more simply

- **Zero-infrastructure retrieval at small scale.** For a few dozen pages, "read the curated index,
  follow links" is genuinely competitive with hybrid search — no models, no index, no schema
  version, nothing to rebuild. Pinakes should stay honest that its machinery pays off only past
  the corpus size where an agent can no longer hold the catalog in context.
- **Anti-rot is enforced, not hoped for.** Orphan pages and unnavigable content are *build
  failures*. Pinakes currently has no equivalent pressure: a doc with an empty sidecar and no links
  indexes fine and just ranks poorly. A `pnk check`-style structural gate (unlinked doc, unused
  tag, dangling `pnk://` target) is cheap and proven valuable here.
- **The write path is fully specified.** Ingest playbook + session ritual + append-only log gives
  every agent session the same shape and makes parallel sessions merge-safe (union-merge log,
  rebase-retry push). Pinakes specifies the engine precisely but the *authoring* workflow much less.
- **Secret scanning sits in the gate**, severity keyed to visibility, with a per-line allow marker
  — directly liftable into Pinakes for any KB that might ever be published.
- **Ownership boundary machinery** (vendored wheel, checksums, copier update) solves fleet-wide
  upgrades — a problem Pinakes sidesteps by being one installed package, but will meet if manifest
  or sidecar schemas ever evolve across many KBs (Pinakes' "no migrations" invariant is the
  opposite bet; ClaudeKB shows what the migration-machinery path costs).
- **Publishing and access control exist at all** — Pinakes has no story for sharing a KB.

## What its experience teaches Pinakes' graph plans

1. **Humans don't author rich links; agents under a gate do author minimal ones.** ClaudeKB gets
   real links written only because a validator *fails the build* without them — and even then it
   demands only reachability, the weakest useful property. Untyped "reachable-from-index" links
   were achievable; nobody built backlinks or typed edges even with the link graph already parsed
   in the validator. Lesson: Pinakes' plan to lean on **free structural edges** (headings,
   co-location, shared tags) rather than hand-authored `links:` entries is the right default;
   treat authored typed links as sparse, precious signal, and consider a check that *nudges*
   (warn on zero-link docs) rather than assuming density.
2. **Agent-driven navigation over plain files works — at fleet-of-small-KBs scale, and because
   the entry point is curated.** The session ritual's "read index.md first" is a hand-maintained
   PageRank prior. It breaks down on: (a) corpus size (the catalog outgrows context; grep replaces
   navigation and precision collapses), (b) cross-KB queries (deliberately unresolvable at
   validation time; unified search deferred), (c) anything needing *ranking* — navigation finds a
   page or doesn't; there is no confidence, no top-k, no abstention. These three failure modes are
   exactly Pinakes' reason to exist; the comparison confirms the niche rather than undermining it.
3. **Path-based identity is ClaudeKB's structural weakness and Pinakes' strongest call.** `kb://`
   links break on file moves (redirect files patch the URL side only, capped by platform limits);
   `pnk://` ULIDs make the graph rename-proof. Any Pinakes graph channel (PPR over edges) inherits
   this robustness for free — edges over ULIDs survive refactors that would sever ClaudeKB's graph.
4. **Curated vocabulary beats folksonomy for the shared-tag edge.** ClaudeKB validates every tag
   against `vocab.yml` precisely to stop tag sprawl. If Pinakes builds shared-tag edges, uncurated
   tags will produce dense noise cliques; a per-KB controlled vocabulary (or an edge-weight
   penalty on high-degree tags) is the proven countermeasure.
5. **Lazy semantic work as a scheduled agent pass is viable.** The `lint` playbook (agent hunts
   contradictions and missing cross-references monthly) is precedent for Pinakes' "lazy LLM
   extraction written back to sidecars": batch, explicit, results persisted in git — not
   per-query magic. It also confirms such passes are a *maintenance* cost model, safely outside
   the free path.
6. **Enforce graph invariants at write time, verify at read time.** ClaudeKB's split — structural
   validators in the gate, semantic sweeps scheduled — maps cleanly onto Pinakes: cheap checks
   (dangling `pnk://`, orphan docs) belong in an indexing-time gate; expensive graph maintenance
   belongs in explicit commands, never inside `pnk search`.

## Key sources

- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/README.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/docs/architecture.md (spec, D1–D18, iteration log)
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/docs/guide/what-is-claudekb.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/docs/guide/using-a-kb.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/docs/guide/public-and-private-kbs.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/docs/guide/roadmap.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/template/CLAUDE.md (the agent contract)
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/src/kbtool/{validators,links,secrets,preprocess}.py
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/src/kbtool/data/playbooks/{ingest,lint}.md
- /Users/luca/Code/repos/github_lucagattoni/ClaudeKB/CHANGELOG.md (v0.1.0–v0.4.0)

*(ClaudeKB's private decision record — `docs/private/` — was not consulted for this document; the
public architecture spec and guides cover everything cited. Deployed-instance hostnames use the
repo's own `example.com` parameterization; no real domains appear here.)*

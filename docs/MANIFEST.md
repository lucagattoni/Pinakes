# Manifest and sidecar reference

The two files you edit by hand. Field-by-field, with defaults taken from `manifest.py` at 0.2.0
(20260728 16:40).

*Why* the format is shaped this way is in [DESIGN §2](DESIGN.md#2-anatomy-of-a-kb); how to use it
is in [GUIDE.md](GUIDE.md). This file is the reference — if a field's default is stated anywhere
else in the repo, that copy is the stale one.

- [`pinakes.toml`](#pinakestoml) — [`[kb]`](#kb) · [`[sources]`](#sources) · [`[embedding]`](#embedding) · [`[extraction]`](#extraction) · [`[chunking]`](#chunking) · [`[retrieval]`](#retrieval) · [`[rerank]`](#rerank) · [`[budget]`](#budget) · [`[[links.kb]]`](#linkskb)
- [The sidecar](#the-sidecar--filepnkyaml)

## Validation rules that apply everywhere

- **Unknown keys are a hard error**, never a silent default. So is the retired `top_k`, rejected by
  name.
- **An explicit empty string is an error**, not a request for the default. Silently substituting one
  hides a mistake until it fails somewhere far away.
- Cross-key invariants are checked at read time, not at use time:
  - widths must narrow: `final_k <= fusion_top_k <= candidates_per_source`
  - `confirm_above_eur <= per_operation_eur`, or the confirmation prompt is unreachable
  - `overlap < max_tokens`
  - confidence thresholds must be ordered, and `fitted_for` is required whenever they are present

---

# `pinakes.toml`

## `[kb]`

**Required.** Identity — nothing can sensibly default it.

| Key | Required | Notes |
|---|---|---|
| `name` | ✅ | Local, human-facing. Rename freely; nothing depends on it |
| `id` | ✅ | ULID. **Permanent.** The authority in every `pnk://` URI. Never edit, never regenerate |
| `template` | | The blueprint and its own version, e.g. `notes@1.0` — the *template's* version, not the package's |
| `created` | | `YYYYMMDD HH:MM` |

## `[sources]`

What gets indexed. Paths are always relative to the KB root, POSIX separators.

| Key | Default | Notes |
|---|---|---|
| `roots` | `["docs/"]` | |
| `include` | `["**/*.md", "**/*.txt"]` | **Add `"**/*.pdf"` yourself** to index PDFs — the shipped template omits it ([GUIDE](GUIDE.md#indexing-pdfs)) |
| `exclude` | `[]` | Applied after `include` |

Sidecars are never ingested as documents, whatever your globs say.

## `[embedding]`

**Required** (`provider`, `model`, `dim`) — the index *is* this model's output, so it cannot be
defaulted.

| Key | Required | Notes |
|---|---|---|
| `provider` | ✅ | `sentence-transformers` or `fastembed`. `init` always stamps the former ([GUIDE](GUIDE.md#choosing-a-backend)) |
| `model` | ✅ | e.g. `BAAI/bge-small-en-v1.5`. **The default model ids are identical on both providers** |
| `dim` | ✅ | Must match the model's real width, or it is a hard error at sync |
| `revision` | | HF commit sha. Pin it once settled; the index refuses to load on a mismatch |

Changing any of these invalidates the index: queries refuse to run and name the remedy. Rebuilding
is free, so this is a stop rather than a cost.

## `[extraction]`

Optional. Governs PDFs only.

| Key | Default | Notes |
|---|---|---|
| `backend` | `pypdfium2` | `pypdfium2` (free) or `claude-vision` (paid; built, but [in no release yet](STATUS.md)). Validated against the registry **without importing either**, so an unknown name is rejected before an extra could matter |
| `model` | | Consulted only when `backend = "claude-vision"` |

Override for one run with `pnk sync --extract=BACKEND`.

## `[chunking]`

| Key | Default | Notes |
|---|---|---|
| `strategy` | `structural` | Headings and paragraphs, not blind character windows. The only value |
| `max_tokens` | `510` | Counted with **the embedding model's own tokenizer**, and validated against its `max_seq_length` minus special tokens. Asking for more is a hard error, not a silent truncation |
| `overlap` | `64` | Must be `< max_tokens` |

Oversize text is **split, never trimmed** — a truncated chunk has an unsearchable tail and nothing
in the output would reveal it.

## `[retrieval]`

| Key | Default | Notes |
|---|---|---|
| `candidates_per_source` | `50` | BM25 top-N *and* vector top-N, before fusion |
| `fusion` | `rrf` | Reciprocal rank fusion, k=60. The only value |
| `fusion_top_k` | `20` | Survivors handed to the reranker |
| `final_k` | `8` | Passages actually returned. `pnk search -k` overrides per query |
| `rerank` | `local` | `local` or `none` |
| `vector_tier` | `auto` | `auto`, `numpy` or `sqlite-vec`. **Only the NumPy tier is built** — `sqlite-vec` is the template release |
| `adjacent_k` | `8` | Neighbours kept per expansion when traversing links, applied **after** ranking. Server-capped at 64 whatever this says, and a value above that is refused at parse time rather than silently clamped. **Not stamped into the template**: `pinakes.toml` hard-errors on an unknown key, so a manifest carrying `adjacent_k` cannot be read by any pinakes released before it existed |

Three separate *pipeline* widths rather than one `top_k` (`adjacent_k` is not one of them — it bounds link traversal, not retrieval), because they are three different cut-offs.

### `[retrieval.confidence]`

Absent by default, and **the shipped template comments it out on purpose**: thresholds fitted
against someone else's corpus are not a calibration. While absent, every result reports
`confidence: unknown`.

| Key | Notes |
|---|---|
| `fitted_for` | `model@revision` of the **reranker** the thresholds were fitted against. On mismatch, `unknown` is reported rather than a wrong number |
| `low_below` | Below this, low confidence |
| `high_above` | Above this, high confidence |

Fit them with `pinakes.calibrate`, which *prints* a block to paste and never writes one.

## `[rerank]`

Consumed only when `[retrieval] rerank = "local"`. Mirrors `[embedding]`.

| Key | Default | Notes |
|---|---|---|
| `provider` | | `sentence-transformers` or `fastembed` — set this too on a `[light]` install |
| `model` | `BAAI/bge-reranker-base` | ~1.04 GB of weights. Same id on both providers |
| `revision` | | HF commit sha |

## `[budget]`

Parsed and validated from v0.1 so a KB authored today stays valid later. **Nothing spends against it
yet** — see [STATUS](STATUS.md#the-surface-you-can-use-today).

| Key | Default | Notes |
|---|---|---|
| `confirm_above_eur` | `0.01` | Prompt for confirmation (soft). Deliberately a *lower*, separate field from the hard caps, and evaluated **once per document**, never per request |
| `per_operation_eur` | `0.05` | Hard ceiling for one invocation — never exceeded, never prompted past |
| `daily_eur` | `1.00` | Hard ceiling per calendar day. A burst limiter between the per-operation and monthly caps: a per-operation cap alone bounds one run, not thirty of them |
| `monthly_eur` | `5.00` | Hard ceiling per calendar month |
| `max_price_age_days` | `30` | Refuse to estimate against bundled prices older than this. An estimate built on silently outdated prices is a liability |
| `timezone` | `UTC` | Makes "daily"/"monthly" unambiguous. Any IANA zone; DST transitions are handled by conversion, not special-casing |
| `on_exceed` | `abort` | `abort` or `partial` |

**The three caps are independent and all three are checked**, in the order above — a run is refused
by the first one it would breach, and a whole-document precheck names *every* blocked cap at once
rather than making you raise one, retry, and discover the next. Raising a cap is a permanent,
ongoing exposure; a one-run `--extract=<backend>` override is not.

Every euro value is parsed as an exact `Decimal`, never a float — a hard cap compared against a
binary approximation of the number you typed is not actually hard. Write them as ordinary TOML
numbers (`0.05`); the exactness is on pinakes's side.

## `[[links.kb]]`

Connected KBs. The schema ships today because IDs cannot be retrofitted; traversal is the links release.

| Key | Notes |
|---|---|
| `id` | The connected KB's ULID — **canonical** |
| `name` | A local alias. Machine-local convenience only |
| `path` | Where it lives on *this* machine |

Aliases live here and **never inside a `pnk://` URI** — a URI carrying an alias would break the
moment the KB reached a machine where that alias means something else.

`path` is stored but **not yet read by anything** — nothing resolves it and no check inspects it.
When it is (the links release), it will be resolved **relative to this KB's root** with `~`
expanded; an absolute path will be accepted and **warned about** by `pnk doctor`, because a
manifest is committed and an absolute path in one publishes your filesystem layout to everyone who
clones it. A path that does not exist on this machine will **not** be an error: a KB is routinely
shared without its partners, and refusing to load would make every connected KB a hard dependency
of every other.

---

# The sidecar — `<file>.pnk.yaml`

One per document, auto-created at first ingest for **every** document, not only linked ones: the
document ID lives here, and an ID that appears only once a doc is linked is an ID you cannot rely
on.

```yaml
id: 01JQ8ZC4V7K2N…            # ULID, assigned once, never regenerated
title: "Attention Is All You Need"
tags: [transformers, architecture]
created: 20260725 09:14
links:
  - to: pnk://01JQ8ZM7…/01JQ8ZD9M…   # <kb-ulid>/<doc-ulid>
    rel: cites
  - to: pnk://self/01JQ8ZE1P…        # `self` is accepted on input, expanded on write
    rel: supersedes
provenance:
  source: https://arxiv.org/abs/1706.03762
  ingested: 20260725 09:14
```

| Key | Written by | Notes |
|---|---|---|
| `id` | sync, once | ULID. **Permanent.** A hand-broken one errors with "restore the original", never a renumber |
| `title` | you | Shown in results |
| `tags` | you | What `pnk search --tag` filters on |
| `created` | sync | Optional; date filters use the document's mtime instead, since every document has one |
| `links[].to` | you / [`pnk link`](CLI.md#pnk-link) | A `pnk://` URI. Aliases and `self` are resolved to ULIDs **on write**, so what reaches disk survives being shared |
| `links[].rel` | you / [`pnk link`](CLI.md#pnk-link) | Free-form relation, e.g. `cites`, `supersedes` |
| `provenance.source` | you | Where the document came from |
| `provenance.extraction` | **sync, paid PDFs only** | `{backend, fingerprint, extracted, content_hash}` |

**Your unknown keys round-trip byte-identically.** The file belongs to you; normalising your fields
away would be data loss. Comments, quoting style, block scalars, blank lines and your own key order
all survive a rewrite, and a value is stored exactly as you wrote it — `country: NO` stays `NO`
rather than becoming `false`.

Bounds on that, all of them things pinakes or YAML does rather than choices about your keys:

| Bound | What happens |
|---|---|
| **Values must be JSON-encodable** | The index stores metadata as JSON. A tag on a *scalar* (`!!binary`, `!!set`, `!!timestamp`, `!!str`, or one of your own), a bare date, or a mapping mixing string and non-string keys is refused at read with a remedy — rather than crashing `pnk sync` later, which is what used to happen. A custom tag on a *mapping* or a *sequence* is fine: it serialises |
| **Indentation follows the writer** | A block sequence **and nested mapping** written `  - item` comes back `- item`. Nothing is lost; the bytes differ |
| **Deleting loses one comment and moves another** | A comment belongs to the construct *before* it, so removing a key or a list entry leaves that comment on whatever replaces it and drops the last one in the block |
| **What YAML does not carry** | CRLF line endings, a byte-order mark, `---`/`...` document markers — and a missing final newline, which is added |
| **An explicit `!!` tag is dropped** | `!!int 3` comes back as `3`. The *value* is unchanged; the tag is not kept |
| **An anchor with no value is dropped** | `mine: &x` with nothing after it loses its `&x`. An anchor on a real value survives |
| **`pnk://self/…` is expanded** | A `self` link is rewritten to the full `pnk://<kb-ulid>/…` form in place — the entry keeps its position, its comment and any keys of your own |
| **A self-referential anchor is not preserved** | `mine: &x` containing `b: *x` reads as `null` and loses its anchor. It used to crash `pnk sync` instead |
| **A reused anchor name is refused** | Every alias to a repeated name would resolve to the last one, so which value it meant is not recoverable |

A **duplicate key is an error**, not a silent last-wins: which of the two values you meant is not
something any tool can recover.

**Sidecars carry no general content hash**, deliberately: one would dirty two files on every
document edit and go stale whenever a document changed without a sync in between. Change detection
belongs to the index.

`provenance.extraction.content_hash` is the narrow exception — it records the file's hash *at the
moment a specific paid extraction ran*, changes only when a fresh paid extraction does, and exists
so a later sync can answer "has this changed since" without depending on any local cache still
existing. It lives in the sidecar rather than the index because `pnk sync --rebuild` reads its
"before" from an empty database, so a backend recorded only in `index.db` is invisible at exactly
the moment a rebuild needs it.

**Sync writes `provenance.extraction` and nothing else into your sidecars**, and only when a paid
extraction actually ran or `--force` discarded one — never for the routine free case. The write is
additive; existing keys survive.

Exactly two things write into `docs/`, and only ever into a sidecar. Sync is the unattended one — it
runs from a git hook and from CI, which is why what it may touch is a single key. The other is
[`pnk link`](CLI.md#pnk-link), which appends one `links[]` entry to the sidecar of the document you
named, and only that one. Neither ever modifies a source document, and neither writes into another
document's sidecar.

Writes are atomic (write beside, then rename): a truncated sidecar would lose a permanent ULID and
every inbound link with it.

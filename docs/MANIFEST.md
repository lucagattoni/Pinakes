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
| `created` | | `YYYYMMDD HH:MM`, **UTC** — stamped by `pnk init`. Naive by design: a KB carried between machines must not disagree about when it was made |
| `requires_pinakes` | | The oldest Pinakes that can read this KB, as a **floor only**: `">=0.6"`. Absent means no floor declared, which is not an error — see below |

### `requires_pinakes` — the compatibility floor

A manifest is forward-**incompatible** on purpose: an unknown key is a hard error, because a typo
that silently left you on defaults is worse than a refusal. The cost is that a KB written by a newer
Pinakes fails on the first key this build has never heard of, and reports it as a spelling mistake
when the user's real problem is an out-of-date Pinakes. This field lets the manifest say so first.

- **Read before every other key**, in a pre-pass over the raw TOML. The ordering is the whole point:
  after strict validation the parse has already died on the unknown key, so the field would be
  unreachable in exactly the case it exists for.
- **A floor only.** `>=` is the sole accepted operator, because a KB is readable by the Pinakes that
  wrote it or any newer one and there is no ceiling to express. `"0.6"`, `"<=0.6"` and `"==0.6"` are
  each refused by name rather than half-honoured.
- **Absence means compatible.** Every KB written before this field existed lacks it.
- **It cannot explain a key retroactively.** A Pinakes built before the field existed has no
  pre-pass and fails on `requires_pinakes` itself. It only ever helps for keys added *after* it
  shipped — which is also why `pnk init` does **not** stamp it: a fresh KB carries no key an older
  Pinakes would choke on, so a stamped floor would lock out readers for no gain.

Nothing updates the field on a KB whose owner never edits it, so it is a lower bound rather than a
promise. The wider design note is [KB-UPDATES.md](KB-UPDATES.md).

## `[sources]`

What gets indexed. `roots` entries are relative to the **KB root**; `include` and `exclude`
patterns are relative to **each `roots` entry** — so with `roots = ["docs/"]`, the pattern matching
`docs/a.md` is `**/*.md`, never `docs/**/*.md`. POSIX separators throughout.

| Key | Default | Notes |
|---|---|---|
| `roots` | `["docs/"]` | Must stay inside the KB: an absolute entry, or one containing `..`, is refused at load |
| `include` | `["**/*.md", "**/*.txt"]` | **Add `"**/*.pdf"` yourself** to index PDFs — the shipped template omits it ([GUIDE](GUIDE.md#indexing-pdfs)). Carries the same containment rule as `roots` (below) |
| `exclude` | `[]` | Applied after `include`. **Not** containment-checked, deliberately |

**`include` must stay inside the KB, and what matters is where a pattern *lands*.** An absolute
pattern is refused (Python's `glob` cannot walk one wherever it points), and so is one whose walk
would leave the KB — checked at load, before anything is globbed. A `..` that lands back *inside* is
fine: `include = ["../notes/*.md"]` from `roots = ["docs/"]` reaches `notes/` and is accepted. What
is refused is `../../outside/*.md`, which used to index files outside the KB and mint sidecars
beside them. A **symlinked directory** inside the KB can carry the walk out with no `..` anywhere,
which no load-time check can see, so the walk re-tests each file and stops at the first one outside,
reporting the pattern.

`exclude` is deliberately exempt: a pattern there can only fail to match, never widen the walk, so
`..` in it is harmless. The asymmetry is intentional rather than an oversight.

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
| `backend` | `pypdfium2` | `pypdfium2` (free) or `claude-vision` (paid, opt-in; [shipped in 0.3.0](STATUS.md)). Validated against the registry **without importing either**, so an unknown name is rejected before an extra could matter |
| `model` | | Consulted only when `backend = "claude-vision"` |

Override for one run with `pnk sync --extract=BACKEND`.

## `[chunking]`

> ⚠️ **Changing any key here needs `pnk sync --rebuild`, and the tool now says so.** An incremental
> sync re-chunks a document only when *the document* changed, so a manifest-only edit reports every
> file `unchanged` and the new setting does nothing on its own. `pnk sync` prints which key moved
> and names `--rebuild`; [`pnk doctor`](CLI.md#pnk-doctor) reports the same as `chunking coherence`
> — the first catches the user who just made the edit, the second the one who made it last week and
> is now asking why `heading_path` is empty. **The warning persists until the rebuild actually
> happens**, never merely until it has been printed once.
>
> An index built before this identity was recorded carries none of it, and that reads as *unknown*,
> never as drifted — so upgrading does not demand a rebuild of every KB for a setting that probably
> never changed.


| Key | Default | Notes |
|---|---|---|
| `strategy` | `structural` | The only accepted value, and **nothing reads it at runtime** — it is validated at parse time and never consulted again. What actually decides chunking is the document's **source type**: `markdown` gets heading and paragraph structure, every other type takes the plain-text path and records no `heading_path` at all. So setting this changes nothing, and it is **not** what turns on the plain-text heading grammar — `headings` below is. It was left inert deliberately rather than given a second value: every manifest ever written already carries `structural`, so defining it now would give an existing value a new meaning retroactively |
| `headings` | `"none"` | `"none"` or `"numbered"`. Which heading grammar runs for the **`text`** source type — and only that type: `markdown` already has one, while `code` and `pdf` are out of scope by decision rather than oversight (the PDF path is *disabled here, never dismantled*, and extending it waits on structure detection worth trusting). `"numbered"` reads a dotted-decimal outline (`1.`, `1.1.`, `2.`) into `heading_path`. **It refuses rather than guesses:** `1.` at line start is also an ordered list, so the numbers must form a valid outline walk across the whole document, and **if the walk fails anywhere that document yields no headings at all** — exactly the pre-grammar behaviour, never a partial labelling. `"none"` is the default and is also writable explicitly, so a manifest can record that the choice was *considered* rather than *predating the feature*. **Not stamped into the template**, same reason as `adjacent_k`: `_toml.py` hard-errors on an unknown key, so a manifest carrying this one cannot be read at all by an older build |
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
| `adjacent_k` | `8` | Neighbours kept per expansion when traversing links, applied **after** ranking. Server-capped at 64 whatever this says, and a value above that is refused at parse time rather than silently clamped. **Not stamped into the template**: `pinakes.toml` hard-errors on an unknown key, so a manifest carrying `adjacent_k` cannot be read by any Pinakes released before it existed |
| `graph_channel` | `"off"` | `"off"` or `"expand"`. With `"expand"` the fused top-*k* become roots, the structural edge set is walked to depth ≤ 2 logical hops, and what it reaches is ranked and fused as a **third** input. **Off, nothing runs** — no query touches `nodes` or `edges`. On over an empty edge set the result is today's two-list fusion *exactly*, by arithmetic rather than approximation. **It ships `off` and its golden-set gate is why** ([STATUS](STATUS.md#did-the-expansion-channel-earn-its-default--no-measured-20260804-2252)). `"ppr"` is not accepted: a manifest that can name a mode the code does not implement is a setting that silently does nothing. **Not stamped into the template**, same reason as `adjacent_k` |

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

Parsed and validated since v0.1 so a KB authored today stays valid later, and **enforced since
0.3.0**: all three caps are checked before each paid call and again for the whole document, and a
breach refuses rather than overspends ([STATUS](STATUS.md#the-surface-you-can-use-today),
[DESIGN §5](DESIGN.md#5-cost-control)).

| Key | Default | Notes |
|---|---|---|
| `confirm_above_eur` | `0.01` | Prompt for confirmation (soft). Deliberately a *lower*, separate field from the hard caps, and evaluated **once per document**, never per request |
| `per_operation_eur` | `0.30` | Hard ceiling for one invocation — never exceeded, never prompted past. Raised from `0.05` on 20260803: at bundled prices a single synthesis round reserves ~€0.21, so the old default refused the first call of any multi-call operation 4× over |
| `daily_eur` | `1.00` | Hard ceiling per calendar day. A burst limiter between the per-operation and monthly caps: a per-operation cap alone bounds one run, not thirty of them |
| `monthly_eur` | `30.00` | Hard ceiling per calendar month. Raised from `5.00` on 20260803 alongside `per_operation_eur`, preserving the ~100-operations-a-month allowance the old pair gave. **`daily_eur` is now the binding sequence limit** — 1.00/day over a 30-day month is 30.00, so the monthly ceiling is reached only by a 31-day month at full daily spend |
| `max_price_age_days` | `30` | Refuse to estimate against bundled prices older than this. An estimate built on silently outdated prices is a liability |
| `timezone` | `UTC` | Makes "daily"/"monthly" unambiguous. Any IANA zone; DST transitions are handled by conversion, not special-casing |
| `on_exceed` | `abort` | `abort` or `partial` |

**The three caps are independent and all three are checked**, in the order above — a run is refused
by the first one it would breach, and a whole-document precheck names *every* blocked cap at once
rather than making you raise one, retry, and discover the next. Raising a cap is a permanent,
ongoing exposure; a one-run `--extract=<backend>` override is not.

Every euro value is parsed as an exact `Decimal`, never a float — a hard cap compared against a
binary approximation of the number you typed is not actually hard. Write them as ordinary TOML
numbers (`0.05`); the exactness is on Pinakes's side.

## `[[links.kb]]`

Connected KBs. The schema ships in v0.1 because IDs cannot be retrofitted; traversal (`pnk links`,
`pinakes_links`) shipped in 0.5.0 and authoring (`pnk link`) in 0.6.0.

| Key | Notes |
|---|---|
| `id` | The connected KB's ULID — **canonical** |
| `name` | A local alias. Machine-local convenience only |
| `path` | Where it lives on *this* machine |

Aliases live here and **never inside a `pnk://` URI** — a URI carrying an alias would break the
moment the KB reached a machine where that alias means something else.

`path` is resolved **relative to this KB's root**, with `~` expanded — never relative to the
directory `pnk` ran from, because a manifest is committed and shared. `pnk sync --scan-links` reads
it, `pnk link` resolves an alias through it, and `pnk doctor` inspects it: an absolute path is
accepted and **warned about**, because a committed absolute path publishes your filesystem layout to
everyone who clones the KB; a path that resolves to nothing at all (`~someone/kb`, an embedded NUL)
is reported with the reason it could not be resolved. A path that does not exist on this machine will **not** be an error: a KB is routinely
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
| `created` | sync | Optional, **UTC**; date filters use the document's mtime instead, since every document has one |
| `links[].to` | you / [`pnk link`](CLI.md#pnk-link) | A `pnk://` URI, ULIDs only. `self` expands to this KB's own ULID on write. An **alias** here is a hard error at read — `pnk link` resolves `<alias>:<path>` on the command line, before anything reaches disk, so what is stored survives being shared |
| `links[].rel` | you / [`pnk link`](CLI.md#pnk-link) | Free-form relation, e.g. `cites`, `supersedes` |
| `provenance.source` | you | Where the document came from |
| `provenance.extraction` | **sync, paid PDFs only** | `{backend, fingerprint, extracted, content_hash}` |

**Your unknown keys round-trip byte-identically.** The file belongs to you; normalising your fields
away would be data loss. Comments, quoting style, block scalars, blank lines and your own key order
all survive a rewrite, and a value is stored exactly as you wrote it — `country: NO` stays `NO`
rather than becoming `false`.

Bounds on that, all of them things Pinakes or YAML does rather than choices about your keys:

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
| **A symlinked sidecar is written through** | The link is kept and its target rewritten, rather than replaced by a regular file. Minting is the exception: it refuses outright |

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

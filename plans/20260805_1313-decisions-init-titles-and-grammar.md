# Decisions — `pnk init` adoption, titles, and the numbered-heading grammar's scope

**Audience: the coder and the planner. Goal: executor.** Three decisions taken by the user
20260805 13:13, after options with trade-offs were put to them. They close the two open corrections
that said *"a decision, then an implementation"* and settle two of the four questions the
numbered-heading grammar could not start without.

## 1 · `pnk init` adopts a directory that already has content

**Decided: refuse only what would actually be overwritten.** Drop the blanket emptiness test.

`init.py:_check_target` currently refuses three things. Two stay, one goes:

| Refusal | Verdict |
|---|---|
| `pinakes.toml` already present — *"is already a KB"* | **Keeps.** A KB's id is permanent; re-initialising would mint a new one and orphan every inbound link |
| the target exists and is not a directory | **Keeps** |
| the directory is **not empty** | **Goes**, replaced by: refuse if any file `init` would write already exists, naming the file |

**Why.** A `.git`, a `README.md` and a `pyproject.toml` already make a directory "not empty", so a
KB could not be initialised inside a cloned repository — which is what
[`20260801_0749-realism-corpus.md`](20260801_0749-realism-corpus.md) prescribes and what everyone
does. **Hit three times independently** (probe rehearsal, dogfooding KB, corpus). The guard's real
purpose is *not scribbling over someone's files*, and a per-file check enforces exactly that and
nothing more.

**The cost, accepted rather than hidden.** The emptiness test was also a cheap typo-catcher: a
mistyped path that happens to exist now gains a KB instead of an error. The damage is bounded —
`pinakes.toml` plus template files, nothing overwritten by construction, trivially deleted — and
the alternative (an `--adopt` flag) makes every user meet the error first and then learn a flag,
which is the complaint rather than the fix.

**Required:** the per-file refusal names the file it found, never a generic "not empty". `docs/GUIDE.md`
gets the retrofit path — how to adopt an existing repository — since that is the case which drove this.

**Test:** a directory holding `.git`, `README.md` and `pyproject.toml` initialises; a directory
already holding a file `init` would write is refused **by that file's name**; a directory holding
`pinakes.toml` is refused as already-a-KB, unchanged.

## 2 · Titles keep the filename fallback, and `pnk doctor` reports it

**Decided: B1 + B3 — keep the honest fallback, add detection. The first-line heuristic is
rejected.**

`sidecar.py:670` mints `title` from the filename stem when nothing supplies one. On the RFC corpus
that gives 300 sidecars reading `title: rfc9110` rather than *"HTTP Semantics"*.

**Why not the obvious fix.** Taking the first non-empty line as a title is cheap and **the corpus
that raised this disproves it**: an RFC's first line is `Internet Engineering Task Force (IETF)`.
It would mint confidently wrong titles at scale, into sidecars the user then commits — and a wrong
title is harder to notice than an obviously-wrong one. A filename is at least visibly a filename.

**Why not per-format extraction.** One grammar per format, each a permanent maintenance surface and
a source of confident errors; PDF metadata in particular is routinely wrong.

**Required:** a `pnk doctor` check reporting documents whose `title` equals the filename stem as
minted — the same shape as the heading-coverage check that resolved the analogous problem:
**detection, never guessing.** It names the count and a sample, so a user knows which documents
need a title rather than discovering it in search results.

**Bounds it must respect.** A title that legitimately equals its filename stem is not a defect —
this is a nudge, not a FAIL. Compare against the *minted* form (stem with `-`/`_` → spaces), not the
raw stem, or every document with a hyphenated filename reads as authored. `title` is documented as
the user's field and stays that way.

## 3 · The numbered-heading grammar — scope and compatibility

Two of the four questions [`20260731_1202-open-corrections.md`](20260731_1202-open-corrections.md)
said had to be answered first. The other two — the value's name, and the false-positive rule — stay
with the planner and must still be written **before** the rule is fitted to any corpus.

### Scope: the `text` source type only

**Decided: `text` only. `pdf` is deferred, not refused.**

A note on the wording, because it matters to whoever builds it: **Markdown is not in scope because
it already works.** `chunk.py` dispatches on source type, and `markdown` already goes through
`_markdown_blocks`. The gap is every *other* type, all of which take `_plain_blocks` and record no
`heading_path`. This decision covers **`text`**, and leaves `pdf` — which takes the same path and
has the same gap — for later.

**Why `pdf` waits.** It is the source type least able to verify its own structure: extracted text
carries no reliable line semantics, so a false heading is both likelier and harder to spot than in
a `.txt` file. **The precondition for extending it is strong structure detection**, not a decision
to revisit the scope — when a PDF's structure can be established rather than guessed, the extension
is a small increment on top of a grammar already proven on text.

> ### 🚫 `pdf` is **disabled here, never dismantled**
>
> **Nothing built for PDF is removed, narrowed, or weakened by this decision.** The user was
> explicit, 20260805. The `[pdf]` extra, the `pypdfium2` extractor, the opt-in Claude-vision path,
> the extraction cache, `path:page` citations, the PDF corpus fixtures and every PDF test stay
> exactly as they are and keep working exactly as they do.
>
> **What this decision does is decline to *extend the new grammar* to `pdf` yet — one gate, in one
> new code path that does not exist.** A PDF continues to be extracted, chunked and indexed today
> precisely as it is now; it simply does not gain numbered-heading detection in this increment.
>
> **If building this appears to require changing any existing PDF behaviour, stop and report it.**
> That is a spec defect, not a task. An increment that "cleans up" PDF handling on the way past has
> misread this decision.

### Compatibility: it sets a `requires_pinakes` floor, explicitly

**Decided: shipping the new `[chunking] strategy` value sets a floor.**

Without one, an older Pinakes meets the new value through `manifest.py`'s `table.choice(...)` and
rejects it as an **unknown value** — which reads as a typo. That is exactly the confusion G4's
`requires_pinakes` exists to prevent: a refusal that can name the version needed instead of
reporting a symptom.

**Required:** a KB whose manifest carries the new value declares a floor, so an older build refuses
with *"this KB requires pinakes >= X"* rather than pointing at the value as if it were misspelled.
**Test:** a manifest with the new value, read by a build below the floor, produces the floor message
and **not** the unknown-value message.

**The accepted cost:** a KB using the new value cannot be read by builds released before it. That is
the correct trade — the alternative is a KB that older builds reject anyway, with a message that
sends the user to fix a spelling mistake they did not make.

## What this does not decide

* The grammar's predicate. `1.` at line start is also an ordered list, and **the rule must be
  written before it is fitted to the RFC corpus**, never derived from it.
* The new value's name.
* Whether to re-run the graph gate afterwards — a separate decision, costing ~2 h of CPU embedding
  plus a `schema_version` 3 rebuild, and carrying the anti-circularity discipline in full if it
  happens.

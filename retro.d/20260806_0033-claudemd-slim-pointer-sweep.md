## Slimming `CLAUDE.md` — a relocation's real cost is its pointers (20260806 00:33)

**HIGH — the reference sweep has to run on the *source file's name*, not on the text that moved.**
Extracting two sections out of `CLAUDE.md` left **seventeen** citations across the tree pointing at
content the file no longer carries. Not one of them quotes the moved wording; they name the file —
`` `CLAUDE.md` calls "the free path stays free" non-negotiable ``, *"the invariant CLAUDE.md gains
says so explicitly"*, *"for the reason CLAUDE.md states"*. A grep for the moved sentences finds
**zero** of them, which is exactly what "keep docs in sync — grep for what changed" instructs you to
run.

The two sweeps measured the difference:

| Sweep | Scope | Found |
|---|---|---|
| Neighbourhood audit, on the moved terms | `docs/`, `tools/` | 4 |
| Second pass, on the string `CLAUDE.md` | whole tree | **13 more**, all in `src/` and `tests/` |

`src/` and `tests/` were never opened by the first pass, because a docs-only change does not look
like it touches them. They held the majority: `embed.py`, `sidecar.py`, `cli.py`, `ids.py`,
`extract/claude.py`, `extract/pageyield.py`, `budget/ledger.py`, and five test docstrings, each
citing an invariant that had just moved to
[`docs/INVARIANTS.md`](https://github.com/lucagattoni/pinakes/blob/main/docs/INVARIANTS.md). The
rule now: **after relocating anything out of a file, `grep -rn '<that filename>'` over the whole
tree and re-judge every hit** — a pointer names its target, so it is invisible to a
content-based search.

**MEDIUM — `docs/INVARIANTS.md` is an index because the facts already had owners.** Before
extracting, each of the nine invariants was checked against the docs that would hold it: **eight
were already stated** in `DESIGN.md` (§1 allowlist, §2.2 sidecar, §3 storage/schema, §5 ledger and
`Decimal`), `MANIFEST.md` (the `id` rows, the round-trip bounds table), `VERIFICATION.md` (§ *The
sidecar round-trip*) or `CLI.md` (`--clear-cache=paid`). A verbatim move would have created a second
copy of eight facts inside the file set whose stated rule is *one fact, one home* — and a second
copy drifts silently, because nothing compares them. So the page links each owner and writes out
only the five implementation rules nothing else states.

**MEDIUM — the no-loss check has to be mechanical.** Normalising every sentence of the old file and
matching it against the new homes flagged 29 candidates: 25 were false positives and **4 were real
losses** — a measured number (`980 RFCs`), the "first time since it opened" qualifier, a plan's
self-description, and the *why* behind *read the clock, never compose a timestamp*, whose only
in-repo home had been the sentence being deleted. Re-reading the diff would not have separated those
four from the twenty-five; only a per-sentence check did.

**Not fixed, out of this change's scope:** `tests/test_extract_claude.py` and
`tools/record_claude_fixtures.py` both still require a **local** `YYYYMMDD HH:MM` for a recording's
`--at`, against the repo's UTC rule adopted 20260804 11:32. One for
[`plans/20260731_1202-open-corrections.md`](https://github.com/lucagattoni/pinakes/blob/main/plans/20260731_1202-open-corrections.md).

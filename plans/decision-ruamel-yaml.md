# Decision: adopt `ruamel.yaml`, replacing `pyyaml` in the sidecar

**Decided 20260731 06:00 (the user), after measurement.**
**Supersedes [`links-and-graph.md`](links-and-graph.md) decision 18**, which was decided
20260729 05:58 on reasoning this measurement contradicts.

This file records the decision and the evidence behind it. **It deliberately does not update any
plan or document** — working out which documents this touches, and what each should say, is the
planning step that comes next. The last section lists what is known to be affected.

---

## The decision

1. **`ruamel.yaml` replaces `pyyaml`** in `src/pinakes/sidecar.py` (round-trip loader, YAML 1.2),
   and in `src/pinakes/eval.py`'s single `safe_load`. Net dependency count unchanged — a swap, not
   an addition. `pyyaml` leaves `[project.dependencies]`.
2. **It lands as its own increment before L6**, not inside it. It is a data-integrity fix to
   existing behaviour; L6 is a new command that depends on it.
3. **L6 then ships without a fallback path.** No `pyyaml` retry, no comment-loss warning, and
   `test_comments_in_the_sidecar_survive_a_rewrite` lands **passing** rather than xfail.

## What decision 18 got wrong

It rested on two claims. Both were checked against the code and the libraries:

**Claim: "a later paid-extraction sync rewrites the same sidecar through pyyaml and destroys the
comments anyway, so the guarantee would be partial either way."** `sidecar.write()` is the only YAML
writer in `src/`, and `sync.py` calls it at four sites: two are `create_sidecar` (minting, where no
sidecar exists and there are no comments to lose) and two are the paid-extraction merge and its
`--force` reversal. **Nothing on the free path rewrites an existing sidecar.** A free-only user's
comments survive indefinitely today, so `pnk link` would be the *first* thing to destroy them. The
"partial either way" argument holds only for a paid-PDF user, on the document they paid to extract.

**Claim: a second YAML library is a poor trade against "core dependencies stay light."**
`ruamel.yaml` 0.19.1 is MIT, a **115 KiB pure-Python wheel with zero required dependencies**, and
ships `py.typed` (so pyright strict needs no stub package). It is lighter than `jinja2`, already
core. That rule's stated target is torch.

## The bug this fixes, which is not about comments

`Sidecar.extra` is documented as *"Keys pinakes does not know. Round-tripped untouched — the file
belongs to the user."* It is not untouched. Reading and rewriting a sidecar through pinakes **as
shipped**:

```yaml
country: NO       →  country: false        # YAML 1.1 booleans
confirmed: yes    →  confirmed: true
shelf: 0755       →  shelf: 493            # octal
duration: 1:30    →  duration: 90          # sexagesimal
```

Under ruamel's 1.2 round-trip all four are byte-identical, because 1.2 reads them as the strings
they visibly are. Today this is reachable only via the paid-extraction rewrite; **L6 is what would
make it routine**, which is why the fix is ordered before it.

## Measurements

Run 20260731 against `ruamel.yaml` 0.19.1 and the committed corpora.

| | Result |
|---|---|
| Committed sidecars round-tripping byte-identically | **51/51**, at ruamel's *default* indent config — it already matches what pinakes' pyyaml writer emits, so adoption produces no diff noise |
| Committed sidecars parsing differently under 1.2 | **0/51** |
| Preserved that pyyaml destroys | comments, quoting style, block scalars (`\|`), blank lines — all four verified lost today |
| Parse cost | 140 µs → **399 µs** per sidecar (2.8× slower). ≈1.4 s → 4.0 s on a hypothetical 10,000-document sync, against an operation that also embeds every chunk |
| `YAML().version = (1, 1)` as a "keep semantics identical" lever | **wrong lever** — it reproduces the corruption exactly (`country: false`, `duration: 90`) *and* injects a `%YAML 1.1` header into every file. The preservation comes from 1.2, not from pinning |

**Known-key safety.** For pinakes' own keys (`id`, `title`, `tags`, `created`, `links`,
`provenance`), 1.1 → 1.2 only ever turns a **hard error into acceptance**: `title: NO` raises
*"must be a string"* today and becomes the string `"NO"`. No KB that syncs today changes meaning.
Anchors and merge keys survive semantically. `isinstance(doc, dict)` and the `str` checks in
`_tags`/`_links` hold unchanged against ruamel's `CommentedMap`.

## The three costs, accepted

1. **A restructure, not a loader swap.** `write()` builds a *fresh* dict and dumps it, which
   discards comments by construction. Preserving them means mutating the loaded document in place,
   so `Sidecar` must carry the original ruamel document opaquely (`None` for a freshly minted one).
   Four construction sites, all inside `sidecar.py`. `with_extraction_provenance` and
   `without_extraction_provenance` enumerate every field by hand today, so a new field would be
   silently dropped by whichever one you forget — `dataclasses.replace` removes that failure mode
   and should land with the change.
2. **Duplicate keys are the one genuine regression.** pyyaml silently takes the **last**; ruamel
   raises. `allow_duplicate_keys=True` takes the **first** — a silent last-vs-first flip, which is
   worse than either. Chosen: let it raise, mapped to `SidecarError`. Consistent with
   `find_duplicate_ids`, which already makes an ambiguous id a hard error rather than guessing.
   It can fail a KB that syncs today, which is the honest cost.
3. **2.8× slower sidecar parse**, as measured above.

## No alternative exists — surveyed, not assumed

| Library | State | Why not |
|---|---|---|
| `ruyaml` | 0.91.0, last release **2021-12-07** | a community fork of ruamel made over the single-maintainer worry; now stale, and it *adds* `distro` + `setuptools` |
| `strictyaml` | 1.7.3, 2023-03 | preserves comments but **drops quoting** (verified); a restricted YAML subset — no flow style, no anchors — so it would reject sidecars `pnk sync` accepts today |
| `rapidyaml` | 0.15.2, 2026-06 | **discards comments at parse** (verified: `# lead\nid: X` → a 2-node tree, no comment node, no comment API) |
| `yamlcore` | 0.0.4, 2024-10 | gives pyyaml the YAML 1.2 core schema, so `NO` reads as `'NO'` (verified) — fixes the *corruption* half with no new parser, but does not preserve comments on dump |
| `oyaml`, `saneyaml` | — | thin pyyaml wrappers |
| `yamlpath` | 3.9.1 | pins `ruamel.yaml==0.19.1` — a consumer, not an alternative |
| `PyYAML-ft` | 8.0.0 | free-threading fork of pyyaml; no comment support |

Non-library routes considered and rejected: a `tree-sitter-yaml` CST for surgical appends (same
silent-corruption risk as hand-rolled text editing, which is the most expensive failure class this
project has had — see the 0.4.1 data-loss fix), and shelling out to `yq` (a Go binary, i.e. an
external runtime dependency in a pip-installable tool).

**Residual risk, named:** `ruamel.yaml` is a single-maintainer project. Mitigated by being MIT,
pure Python, zero-dependency and 115 KiB — vendorable or forkable if it ever stalls. `ruyaml` shows
forking is feasible even though that fork itself died.

---

## Known to be affected — for the planner, not yet done

Neither the edits nor their wording are decided here. This is the list of places a claim about
YAML, comments, or `extra` is known to live; **audit the neighbourhood of each rather than only the
named line.**

- **`plans/links-and-graph.md`** — decision 18 and its row in *What this plan deliberately does NOT
  decide*; L6's description (the xfail test, the comment-loss warning, the `ruamel` sentence); the
  L6 test list; the DESIGN §2.2 amendment row; the increment ordering, which now has a new
  increment before L6; L8's verification steps if any name a YAML behaviour.
- **`docs/DESIGN.md` §2.2** — carries the deferral explicitly: *"PyYAML drops comments and re-sorts
  unknown keys on this one write … a comment-preserving writer is `pnk link`'s problem (the links
  release), not pulled forward here."* Also the surrounding paragraph on `provenance.extraction`
  being the one case where sync rewrites an existing sidecar.
- **`docs/MANIFEST.md`** — the sidecar field reference, wherever it describes unknown-key handling.
- **`pyproject.toml`** — `[project.dependencies]`, and any CI matrix leg that names yaml.
- **`CLAUDE.md`** — the *Tooling* section if a dependency rule needs qualifying, and possibly a new
  invariant: an unknown key in a sidecar round-trips **byte-identically**, which is a stronger and
  more testable promise than "untouched".
- **`docs/VERIFICATION.md`** — rows for whatever the new increment asserts.
- **`docs/STATUS.md`** — if it names the YAML library or the deferral anywhere.
- **`src/pinakes/sidecar.py`** — the module docstring and `Sidecar.extra`'s own docstring, which
  makes the claim this decision found to be false.

Ordering is settled: the swap is its own increment, then L6.

---

## Measurement review — 20260731 06:25

The decision above stands. Its measurements were re-run independently, and the swap was prototyped
against the real suite in a throwaway worktree: **871 of 872 tests pass**. The sections above are
left as they were written; this section records where the evidence differs, because an executor
building from those claims alone would build the wrong thing.

### Confirmed exactly as written

51/51 byte-identical round-trip · 0/51 parse differently · the four corruptions are real ·
`DuplicateKeyError` is a `YAMLError` subclass, so the existing `except` clause catches it unchanged ·
no warnings under `filterwarnings = ["error"]` · comments, blank lines, block scalars, anchors and
unicode all survive · **freshly minted output is byte-identical to PyYAML's** across seven shapes,
so adoption causes no fixture churn · both `eval/questions.yaml` parse identically, making the
`eval.py` swap inert · and the predicted silently-dropped field **reproduced**: both provenance
helpers returned `original=None` and destroyed the comments until `dataclasses.replace` replaced the
hand-enumerated constructors.

### Four claims corrected

| Claim | What measurement shows |
|---|---|
| *"51/51 at ruamel's **default** config"* | True for indentation, **false for quoting and line width**. At the default, `q: "quoted"` → `q: quoted`, and a value past 80 columns is wrapped onto a continuation line — which PyYAML does **not** do. A default-configured swap is a fidelity **regression**. `preserve_quotes = True` and `width = 4096` restore both, and still give 51/51 and still give byte-identical minted output |
| *"1.2 reads them as the strings they visibly are"* | True of `NO`, `yes` and `1:30`; **false of `0755`**, which becomes int `755` — not the string, not PyYAML's octal `493`. The file still round-trips byte-identically because ruamel preserves the representation, so the promise holds; the explanation does not |
| *"ships `py.typed` (so pyright strict needs no stub package)"* | **False under this project's settings.** `YAML.load` and `YAML.dump` carry an untyped `stream` parameter, which `reportUnknownMemberType` rejects: 2 errors. A `cast` does not help — pyright flags the member access before the cast applies |
| *"`pyyaml` leaves `[project.dependencies]`"* | It leaves core, but **cannot leave the project**: eight files under `tests/` and `tools/` import it (`test_ci.py` parses workflows, `link_density_gate.py` reads sidecars, `test_partner_kb.py` writes fixtures). It moves to `[dependency-groups] dev` |

### Five behaviours the decision did not anticipate

1. **ruamel accepts documents PyYAML rejects.** `{id: x, : }` — an empty key — is valid YAML 1.2.
   This is the one failing test. The widening is in **syntax**, not only in scalar resolution.
2. **A non-string top-level key crashes `write()` — on `main`, today.** `id: X` plus `123: v` plus
   `abc: w` reads fine under PyYAML and then dies in `sorted()` comparing `int` to `str`. A live
   bug, independent of this decision, and this increment is the right place to close it.
3. **Canonical ordering and byte-identical round-trip are mutually exclusive.** `write()` sorts
   `extra` alphabetically today; a file whose keys are not already alphabetical cannot be both
   re-sorted and preserved. Resolved by scoping canonical order to **minting** only.
4. **Deleting a commented key orphans its comment.** ruamel attaches a comment to the *preceding*
   key, so `del document["provenance"]` leaves the comment describing whatever follows. Inherent to
   the model — it gets a pinning test and a documented limitation, not a fix.
5. **The `DuplicateKeyError` message ends with `To suppress this check see: <ruamel URL>`**, which
   would reach a user inside a `SidecarError` and recommend precisely the behaviour this decision
   rejected.

Also: through pinakes' own `read()` → `write()` it is **50/51**, not 51/51 — `pnk://self/…` expands
to a ULID in `tests/partner-kb/docs/outgoing-loans.md.pnk.yaml`. That is pinakes' documented
normalisation of a *known* key, not a regression, and it is why the new invariant is scoped to
**unknown** keys. CRLF, a BOM and `---`/`...` document markers are likewise normalised away, and the
invariant names those exclusions.

### The stub hazard, demonstrated

The chosen answer to pyright is a local stub under `stubs/` (the `stubs/pypdfium2.pyi` precedent),
which reaches **0 errors with 0 suppressions**. It carries one sharp edge, found the hard way:

> A stub *overrides* the real package, so pyright validates against the stub's fiction. Declaring
> `DuplicateKeyError` importable from `ruamel.yaml` gave **0 pyright errors** and an `ImportError`
> at runtime. Correcting it to `ruamel.yaml.error` gave **0 pyright errors** and an `ImportError`
> again. It lives in `ruamel.yaml.constructor`.

Twice green on code that could not run. The stub therefore ships with a test that imports every
symbol it declares — a gate is only as true as the fiction it checks.

### Decisions taken on the back of this review — 20260731 06:25 (the user)

| # | Decision |
|---|---|
| 19 | **Non-string top-level keys are refused at `read()`**, with a `SidecarError` and a remedy — top level only, since that is exactly the mapping pinakes partitions into `KNOWN_KEYS`/`extra`. It makes `extra: dict[str, Any]` honest, matches what `sidecar.py` already does with every other type violation, and closes behaviour 2 above at its cause. Separately, `test_malformed_sidecars_are_rejected`'s `{id: x, : }` fixture is **replaced by `{id: x`** (an unclosed flow map, which both libraries reject): that case exists to exercise the parse-error branch, and flipping its assertion would leave the branch untested |
| 20 | **pyright is satisfied by a local stub plus an import-verification test**, not by inline suppressions — v0.1 rule 7 holds literally |
| 21 | **A subprocess `sys.modules` gate proves `src/` never imports `pyyaml` again**, reusing `tests/free_path_run.py`'s technique. A grep would miss a lazy or indirect import, which is the lesson the paid-path gate already paid for |
| 22 | **The release is MINOR — at whatever number is next when it is cut** — with the behaviour changes called out explicitly in `CHANGELOG.md`. Pre-1.0 SemVer carries breaking changes in MINOR, and 1.0.0 stays reserved for an actual surface freeze. *(A number is deliberately not written here: CLAUDE.md's 🚫 rule forbids numbering unbuilt work, and the first draft of this row broke it.)* |

---

## Adversarial review — 20260731 07:10

Two independent reviewers, both reproducing every claim by running code. **Verdict: not implementable
as written** — eight HIGH findings. Several corrected the *measurement review above*, which is why
this section exists rather than an edit in place.

### What the reviewers refuted in this document

| Claim (above) | Measurement |
|---|---|
| *"PyYAML does not wrap"* | **Refuted.** PyYAML's emitter has `best_width = 80` and folds plain *and* single-quoted scalars. It declines only when the scalar offers no break opportunity — which is why an unbroken `"x" * 100` test fooled the first pass. Both libraries wrap a long *spaced* value, at different break points, so neither round-trips it at default width. `width = 4096` therefore **exceeds** PyYAML rather than restoring parity: a defensible choice, but a different one |
| *"Minted output is byte-identical to PyYAML's"* | **Refuted as a general claim** — 49 of 57 shapes, not 7 of 7. `None`, an embedded newline, an empty key name, a long spaced value, and five 1.1-ambiguous scalars all differ. See decision 23 |
| *"1.1 → 1.2 only ever turns a hard error into acceptance"* (decision body, *Known-key safety*) | **Refuted.** It runs both ways: `1e3` and `1E3` resolve to `float` and `0o17` to `int` under 1.2, where PyYAML 1.1 leaves all three as **strings**. `_optional_str` raises on a non-`str`, so `title: 1e3` and `created: 0o17` **sync today and hard-error after L5b** — a third breaking line |
| *"A `cast` does not help"* | **Refuted as written.** Casting the *result* or the *bound method* fails, as stated. Casting the *instance* — `cast(Any, _yaml()).load(raw)` — reaches 0 errors with 0 suppressions and no stub. The stub is still the better engineering choice, because `cast(Any, …)` erases the whole surface rather than describing it; decision 20's *reason* was wrong |
| *"An import-verification test closes the stub hazard"* | **Insufficient.** A stub declaring `load(self, stream, strict: bool = False)` is pyright-green, passes an importability check, and `TypeError`s at runtime. `stubs/pypdfium2.pyi` transcribes signatures via `inspect.signature`; this stub's gate must compare signatures, not just resolve names |
| *"Deleting a commented key orphans its comment"* | **Understated.** Deleting `provenance` misattributes its leading comment to the next key **and silently deletes the following key's own comment**, because that comment is stored as `provenance`'s trailer. That is comment *loss*, not only misattribution |
| *"The `eval.py` swap is inert"* | **Overreaches.** True of the two committed `questions.yaml`. `load_questions` (`eval.py:111`) has no `try/except`, so a duplicate key in a *user's* golden set goes from silent last-wins to an uncaught `DuplicateKeyError` out of `make eval` |
| *"`compare=False` … or every equality assertion silently changes meaning"* | **Wording refuted, with a consequence that matters more.** `CommentedMap.__eq__` ignores comments, so including `original` would fail *loudly*, not silently. The consequence: **no equality assertion can ever detect comment loss** — every comment-preservation test must compare file **bytes** |
| *"50/51 through pinakes' own read → write"* | **Already true on `main` today, under PyYAML.** It is a regression net against fixture churn, not evidence for ruamel |
| *"51/51 … and still gives 51/51 at the tuned config"* | **Carries no information.** The corpus has zero comments, zero quote characters, zero lines over 80 columns and no unknown keys, so it exercises neither setting |
| *"140 µs → 399 µs (2.8×)"* | **2.09×** (135 µs → 282 µs) when the `YAML()` instance is reused. 399 µs is reproducible only by constructing one per call — which `_yaml()` as sketched does |
| *"115 KiB"* | Correct for the **wheel**; the installed footprint is 549.5 KiB. Every other part of the survey — MIT, `py3-none-any`, no compiled artifacts, empty required-dependency set, lighter than `jinja2` — confirmed exactly |

### What the reviewers found that neither document had

**An unknown YAML tag becomes an unhandled traceback out of `pnk sync`.** `shelf: !mytag A12` is
refused today as a clean `SidecarError` (PyYAML's `ConstructorError` is a `YAMLError`). ruamel's
round-trip loader accepts it as a `TaggedScalar`; `extra` carries it into `_metadata()`
(`sync.py:1273`) and `store.dumps_metadata` → `json.dumps` raises `TypeError`. `sync.py` contains no
`except TypeError` and no `except Exception`. See decision 24.

**`write()`'s specification was under-determined, and the literal reading loses nested comments.**
The known keys are currently rebuilt wholesale (`document["provenance"] = dict(...)`), so an executor
who changes only *what `document` is* satisfies every word of the first draft and destroys any
comment **inside** `provenance:` or `links:` — the one block the only existing rewrite path writes
to. No test in the first draft's list would have caught it.

**The `sys.modules` gate could not prove the claim attached to it.** `pinakes.eval` is not in the
free CLI path's import graph (verified: `pinakes.template` is the only `pinakes.*` module the harness
loads), so leaving `import yaml` in `eval.py` — one of the two modules L5b migrates — keeps the gate
green.

Also: a substring predicate false-positives on `pydantic_settings.sources.providers.yaml`, which the
free-path module list really does contain (`tests/test_paid_path.py` already fixes this class of
mistake for `google.protobuf`); `ruamel.yaml.safe_load()` is **removed** in 0.19 and fails as an
`AttributeError`, not a warning; and `sorted()` crashes on `bool`, `None`, `float` and `date` keys
too, while a **single** non-string key writes back fine today — so it is the single-key case that is
the breaking one.

### Decisions taken on the back of the review — 20260731 07:10 (the user)

| # | Decision |
|---|---|
| 23 | **A minted sidecar quotes any scalar YAML 1.1 *or* 1.2 would resolve to a non-string.** `skeleton()` derives the title from the filename stem, so `NO.md` mints `title: NO`, which ruamel writes bare and every 1.1 reader — including `tools/link_density_gate.py` — reads back as `False`. Today PyYAML quotes it. Verified: single-quoting the union of both resolvers restores today's output on 23 of 26 shapes and makes the other three (`1e3`, `1E3`, `0o17`) *safer* than today, because a quoted value cannot become the third breaking line. Only what pinakes **writes** is covered; a hand-written bare `NO` round-trips as the user wrote it |
| 24 | **A tagged node is refused at `read()`**, restoring today's behaviour exactly — PyYAML rejects `!mytag` on scalars, mappings and sequences alike. The detector must cover **both** shapes: `TaggedScalar` for a tagged scalar, and `node.tag.value is not None` for a tagged `CommentedMap`/`CommentedSeq`. A `TaggedScalar`-only check misses `shelf: !mymap {a: 1}` — which happens to serialise, so it is a silent widening rather than a crash |
| 25 | **L5b cuts its own MINOR release, named — never numbered — *the sidecar-fidelity release***, added to the unbuilt-work tables in `CLAUDE.md` and `docs/STATUS.md`. Complete, breaking, self-contained work does not wait for L6–L8. The plan's *Two releases* section becomes three |

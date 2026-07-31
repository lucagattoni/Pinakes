# Decision: adopt `ruamel.yaml`, replacing `pyyaml` in the sidecar

**Decided 20260731 06:00 (the user), after measurement. Supersedes
[`links-and-graph.md`](links-and-graph.md) decision 18.** Revised 06:25, 07:10 and 07:45 as
measurement and two adversarial passes corrected it; this file states the current position only.
**Built by L5b and L5c** — split 20260731 07:52 (decision 28) after three passes returned 8, 8 and 7
HIGH on one section. **L5b** is the swap and everything needed to keep behaviour
equivalent — decision 26 included, because without it L5b alone turns a clean `SidecarError` on an
unknown tag into a traceback. **L5c** is decision 19 alone. L5b takes the interim cut.

## The decision

1. **`ruamel.yaml` replaces `pyyaml`** in `sidecar.py` (round-trip loader, YAML 1.2) and in
   `eval.py`'s single `safe_load`. A swap, not an addition: `pyyaml` leaves
   `[project.dependencies]` for `[dependency-groups] dev`, where eight files under `tests/` and
   `tools/` still need it.
2. **Its own increment before L6**, which is a new command depending on it.
3. **L6 ships no fallback** — no `pyyaml` retry, no comment-loss warning, and
   `test_comments_in_the_sidecar_survive_a_rewrite` lands passing.

Decision 18 rested on two claims, both measured false. *"A later paid-extraction sync destroys the
comments anyway"* — `sidecar.write()` is the only YAML writer in `src/`, and nothing on the free path
rewrites an existing sidecar, so `pnk link` would be the **first** thing to destroy a comment.
*"A second YAML library is a poor trade against core dependencies staying light"* — it is not a
second library but a replacement, and `docs/KB-UPDATES.md` §5 had already argued for `tomlkit` in
core on exactly this trade.

## The bug this fixes, which is not about comments

`Sidecar.extra` is documented *"round-tripped untouched"*. It is not:

```yaml
country: NO       →  country: false        # YAML 1.1 booleans
confirmed: yes    →  confirmed: true
shelf: 0755       →  shelf: 493            # octal
duration: 1:30    →  duration: 90          # sexagesimal
```

Under 1.2 all four round-trip byte-identically. Three read as the strings they visibly are; `0755`
becomes int `755` and survives because ruamel keeps the representation. Reachable today only through
the paid-extraction rewrite — **L6 is what would make it routine**.

## Measurements

`ruamel.yaml` 0.19.1 against the committed corpora, plus a prototype of the full swap: **871 of 872
tests pass**.

| | Result |
|---|---|
| Committed sidecars round-tripping byte-identically | **51/51** — but the corpus has no comments, no quotes and no line over 78 columns, so it exercises neither tuning setting below |
| Required configuration | `preserve_quotes = True` and `width = 4096`. At the defaults, quoting is dropped and a *spaced* value folds at column 80. PyYAML folds at 80 too, so `width` **exceeds** PyYAML rather than restoring parity |
| Preserved that pyyaml destroys | comments, quoting, block scalars, blank lines. **Not** preserved: indentation, which ruamel re-indents to its dumper settings; CRLF; a BOM; `---`/`...`; the `!` non-specific tag |
| Minted output vs PyYAML's | **49/57** shapes identical — the gap is why decision 23 exists |
| Parse cost | 135 µs → **282 µs** per sidecar (2.09×) with the `YAML()` instance reused; 399 µs if constructed per call |
| `YAML().version = (1, 1)` as a "keep semantics identical" lever | **wrong lever** — reproduces the corruption *and* injects a `%YAML 1.1` header |
| `ruamel.yaml` 0.19.1 | MIT · 115 KiB wheel (549 KiB installed) · `py3-none-any` · no compiled artifacts · empty required-dependency set · lighter than `jinja2`, which needs `MarkupSafe` |

**1.1 → 1.2 runs both ways.** `title: NO` goes from hard error to acceptance, but `1e3`, `1E3` and
`0o17` are *strings* to PyYAML 1.1 and *numbers* to 1.2, so `title: 1e3` **syncs today and
hard-errors after**. Anchors and merge keys survive semantically **in the YAML**, but not in the index: a boolean
carrying an anchor returns `ScalarBoolean`, an `int` subclass, which encodes as `1` where PyYAML
wrote `true` — hence the coercion in L5b item 3. `isinstance(doc, dict)` and the `str` checks hold
against `CommentedMap`.

**Four breaking changes**, and separately **four crashes that become named errors** — `!!binary`,
`!!set`, `!!timestamp` and a bare date all raise an unhandled `TypeError` from `json.dumps` today.

| Breaking | Was |
|---|---|
| A duplicate key | silent last-wins |
| A non-string top-level key | worked, unless mixed types made `sorted()` raise |
| A string field 1.2 resolves as a number (`1e3`, `0o17`) — `title`, `created`, `tags[]`, `links[].to`, `links[].rel` alike | a string |
| An `!!str`-tagged value | worked |

## Decisions

| # | Decision |
|---|---|
| 19 | *(L5c)* **Non-string top-level keys refused at `read()`**, with a remedy. Top level only — that is the mapping pinakes partitions into `KNOWN_KEYS`/`extra`. It makes `extra: dict[str, Any]` honest and closes a `TypeError` live on `main` today. `test_malformed_sidecars_are_rejected`'s `{id: x, : }` fixture becomes `{id: x`, which both libraries reject, so the parse-error branch stays covered |
| 20 | **A local stub under `stubs/`, plus a signature-comparison test.** `py.typed` does not satisfy pyright strict here: `load`/`dump` carry an untyped `stream`. `cast(Any, _yaml()).load(...)` also reaches zero errors but erases the whole surface. An *import*-only check is insufficient — a stub declaring a parameter ruamel lacks is pyright-green and `TypeError`s at runtime |
| 21 | **An AST scan over `src/pinakes` proves `pyyaml` never returns**, paired with the existing runtime check. An import walk was specified first and is wrong twice: it loads `pypdfium2` (absent on the `[light]` leg, and probing a backend by loading it is forbidden), and it executes module scope only, so the lazy import it exists to catch is invisible to it |
| 22 | **MINOR, at whatever number is next when cut.** No number is written here — CLAUDE.md forbids numbering unbuilt work |
| 23 | **Every scalar pinakes writes is single-quoted when ambiguous** — minted or newly assigned into an existing document, keyed on *the value being assigned*, never on `original is None`. `skeleton()` derives the title from the filename stem, so `NO.md` otherwise mints a bare `title: NO` that a 1.1 reader takes as `False`; `pnk link --rel no` is the same hazard on an existing file. Predicate: the union of `yaml.resolver.Resolver` and `VersionedResolver` at `(1,1)` and `(1,2)` — anything not resolving to `…:str` in all three. Scalars pinakes did not author are left as the user wrote them |
| 26 | *(L5b)* **Every value under `extra` and `provenance` must be JSON-encodable**, else `SidecarError`. This is the constraint the index imposes (`store.dumps_metadata` → `json.dumps`), so it tests the real thing rather than a tag taxonomy, and reaches tagged **keys** at any depth. Documented widening: a tagged *mapping* or *sequence* serialises and is now accepted where PyYAML refused it |
| 28 | **L5b splits into L5b and L5c.** The seam is what the library does versus what pinakes chooses to reject. All the churn across three passes was at the interfaces inside one oversized increment; L5c is independently revertible |
| 27 | **The links release cuts twice** — an interim MINOR at L5b carrying L1–L5b, and the final cut at L8. A tag is a point on `main`, so a cut at L5b ships everything merged before it; naming it after one increment would have been false |

*(24 and 25 were taken and superseded the same day — by 26 and 27 respectively. A tag detector was
both over- and under-inclusive; a third named release was impossible, since a tag cut at L5b ships
L1–L5 whatever it is called.)*

## Alternatives — surveyed, not assumed

| Library | Why not |
|---|---|
| `ruyaml` | last release 2021-12-07; *adds* `distro` + `setuptools` |
| `strictyaml` | drops quoting; a restricted subset that would reject sidecars `pnk sync` accepts today |
| `rapidyaml` | discards comments at parse |
| `yamlcore` | fixes 1.1 semantics for pyyaml, but does not preserve comments on dump |
| `oyaml`, `saneyaml` | thin pyyaml wrappers |
| `yamlpath` | pins `ruamel.yaml==0.19.1` — a consumer |
| `PyYAML-ft` | free-threading fork; no comment support |

Rejected non-library routes: a `tree-sitter-yaml` CST for surgical appends (the hand-rolled-text
failure class that produced the 0.4.1 data-loss fix), and shelling out to `yq` (a Go binary).

**Residual risk:** single-maintainer project. Mitigated by MIT, pure Python, zero-dependency and
115 KiB — vendorable or forkable.

## Two lessons, for `retro.d/` when L5b lands

**A stub overrides the real package, so pyright validates the stub's fiction.** Declaring
`DuplicateKeyError` in `ruamel.yaml` gave 0 errors and an `ImportError`; correcting it to
`ruamel.yaml.error` gave 0 errors and an `ImportError` again. It lives in `ruamel.yaml.constructor`.

**A third instance of the increment-shaped blind spot** CLAUDE.md already records from I5 and I6a:
the pass that specified the comment-preservation tests wrote fixtures whose comments were all
top-level, so every test passed on an implementation that destroyed nested ones.

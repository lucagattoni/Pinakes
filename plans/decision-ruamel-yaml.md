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

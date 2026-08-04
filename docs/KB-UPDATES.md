# Updating an existing KB — design note

**Status: mostly proposal. Decided 20260728 18:39.** Its minimum — the `requires_pinakes` pre-pass
(§4, §7) — **shipped in 0.6.0**, as G4 of
[`plans/20260729_0256-links-and-graph.md`](../plans/20260729_0256-links-and-graph.md); every field rule is in
[MANIFEST.md](MANIFEST.md) and the reasoning in [DESIGN §2.1](DESIGN.md#21-the-manifest--pinakestoml).
Everything else here — `pnk upgrade`, the template-drift gate, doctor reporting drift — is still a
proposal, and `pnk upgrade` stays template-release work. [STATUS.md](STATUS.md) is the authority on
what exists.

This note answers one question the build plans had not asked: **when pinakes changes, what happens
to a KB somebody already has?**

---

## 1. The problem

A KB is two things with opposite update stories. `.pinakes/` is **derived** — throw it away and
rebuild, free and deterministic. `pinakes.toml`, `docs/` and the sidecars are **committed**, hand-
edited, and belong to the user; nothing may rewrite them casually.

The design handles derived state well and committed state not at all. Every mechanism below exists
for the first category. For the second there is one deferred command (`pnk upgrade`, the template release) and no
detection at all — while v0.2 is actively changing what the template ships.

## 2. The four drift axes

| # | What drifts | Mechanism today | State |
|---|---|---|---|
| 1 | **Index schema** | `schema_version` mismatch → refuse to open, name `pnk sync --rebuild`. No migrations, by design (`store.py:205`) | ✅ shipped |
| 2 | **Embedding model** | Index built by another model/revision → queries refuse rather than return garbage | ✅ shipped |
| 3 | **PDF extractor** | Fingerprint mismatch → free backend refuses; paid marks `stale_extraction` and warns | ✅ shipped (I5) |
| 4 | **Manifest + template** | `[kb] requires_pinakes`: a version floor read in a pre-pass, so a refusal can name the version needed (G4, shipped 0.6.0). The template half — detecting and adopting drift — is still absent | ◐ **half closed** |

Axes 1–3 share a shape: *detect, refuse, and point at a free remedy.* That works because the remedy
is always "rebuild derived state", which costs nothing and destroys nothing.

Axis 4 cannot borrow it. The remedy is "change a file the user owns", which is neither free nor
safe by default — so the mechanism has to be different in kind, not merely deferred.

## 3. The gap is live, not theoretical

Three concrete cases on `main` today:

1. **The PDF glob.** `pnk init` stamps `include = ["**/*.md", "**/*.txt"]`. A PDF dropped into a KB
   is silently skipped — sync prints `0 indexed` and explains nothing. I9 adds `**/*.pdf` to the
   *template*, which only affects `pnk init`, so **every KB created before I9 stays PDF-blind
   permanently.** v0.2's headline feature never reaches them.
2. **I6a's budget keys.** `daily_eur` and `max_price_age_days` landed with defaults, so existing KBs
   keep working — but a KB whose owner *sets* one is then unreadable by any earlier pinakes
   (§4).
3. **The one drift signal that exists does not fire.** `doctor._template` compares declared version
   strings only (`doctor.py:135`), and I9 as drafted changes template content without bumping
   `template.toml`'s `version = "1.0"`. A rule with no gate; it already lapsed before shipping.

## 4. Compatibility posture

Verified behaviour when a file contains a key the running pinakes does not know:

| File | Behaviour | Direction |
|---|---|---|
| **Sidecar** | Preserved verbatim under `extra` and written back (`sidecar.py:35,106`) | Forward-**compatible** |
| **Manifest** | **Hard error** (`_toml.py:184`) | Forward-**incompatible** |
| **Index** | `found != str(SCHEMA_VERSION)` (`store.py:205`) | Refuses **both** directions |

Demonstrated against `main` (20260728 18:39) with a hypothetical future key:

```
REFUSED: [budget]: unknown key(s): `weekly_eur`
REMEDY : Unknown keys are rejected rather than ignored — a typo would otherwise leave you
         with default behaviour while believing you had configured something.
```

The refusal is correct; **the diagnosis is wrong.** The user's problem is an out-of-date pinakes,
and the message tells them they made a spelling mistake.

### Decided

- **Downgrade is unsupported.** A KB may be opened by the pinakes that wrote it, or newer. An older
  one refuses, **naming the version required**. This makes explicit what `store.py` already does.
- **Strictness is unchanged.** Unknown keys stay a hard error — the typo protection is worth more
  than graceful degradation, and cross-version sharing is not a goal.
- **`[kb]` gains `requires_pinakes`** — **built in G4** — e.g. `">=0.3"`, so the refusal states the
  remedy instead of the symptom. A floor only: `>=` is the sole operator, since the posture above
  has no ceiling to express. Absence means no floor declared:

  ```
  error: this KB requires pinakes >= 0.3 (this build is 0.2.1)
  ```

  The cost, accepted: it couples the KB format to package version numbers, which the project
  deliberately avoided for *templates*. The reasoning that makes it acceptable is that the template
  decoupling exists so a package upgrade never silently changes a KB's blueprint — a compatibility
  floor changes no blueprint. An actionable error was judged worth the coupling.

## 5. `pnk upgrade`

Diffs the KB's recorded template version against the installed one.

**Does:**

- print the diff, always, before doing anything;
- with `--apply`, write the additive changes into `pinakes.toml`, **preserving comments** — the
  shipped manifest is mostly explanatory comments, and losing them would strip the guidance the
  template exists to deliver. Via `tomlkit` (MIT, zero dependencies, 197 KB — against `numpy`'s
  19.4 MB and `mcp`'s ~17 transitive dependencies already in core), **added to core**;
- update `requires_pinakes` when it writes.

**Must never:**

- touch anything under `docs/` — not a document, not a sidecar;
- renumber or regenerate any ULID;
- re-chunk, re-embed or re-extract as a side effect. A changed `include` glob means new documents
  exist to index, and that is `pnk sync`'s job, invoked separately and explicitly;
- apply anything without `--apply`, or without having printed it first.

The precedent it follows is `pnk doctor --prune`: print every path, then act only on request.

## 6. Detecting template drift

A CI gate hashes the template directory and fails when **content changed without a version bump**,
and when a version bumped with no content change. `template.toml`'s `version` stays the
human-readable contract; the hash is what makes the contract enforceable.

Scope: **everything under `templates/<name>/` except an ignore-list** (`README.md`, and
`template.toml` itself, which carries the version being compared). Inverting the list is deliberate
— an explicit *include*-list would need extending whenever a template gains a consumed file, which
is the same rule-without-a-gate failure this gate exists to prevent. Fail-safe: a new file is
covered by default, and only prose is exempt.

The gate runs at commit time, so it produces no warnings in any user's KB.

## 7. Implementation constraints

- **`requires_pinakes` must be read in a pre-pass, before strict validation.** Otherwise the parse
  dies on the first unknown key and the good error never fires — the field would be unreachable in
  exactly the case it exists for. This is the one non-negotiable ordering requirement.
- **Its absence means compatible, never an error.** Every KB in existence lacks the field; a missing
  floor is "no floor known", not a refusal.
- The template-drift gate needs no runtime support in a user's KB — it compares repo content against
  a declared version, entirely inside CI.

## 8. Open questions

- **Does an increment's manifest addition oblige a `requires_pinakes` bump?** Additive keys with
  defaults do not break a *newer* reader, but strictness means an older reader fails on them the
  moment a user sets one. A rule is needed: probably "bump when a key is added", accepting that this
  tracks feature releases closely.
- **What updates `requires_pinakes` on a KB whose owner never runs `upgrade`?** Nothing does, so the
  floor reflects the last write. That is honest but means the field is a lower bound, not a promise.
- **Should `doctor` report available template upgrades?** Detection is cheap and report-only; it
  would make the gap visible without waiting for `pnk upgrade`.
- **Multi-template ecosystem** (the template release) multiplies all of this by the number of templates.
- Small follow-up: the unknown-key remedy still points at `docs/DESIGN.md §2.1`, whose field tables
  moved to [MANIFEST.md](MANIFEST.md) in 0.2.1.

## 9. Scope — undecided

Deliberately not assigned. The cheapest useful subset, in dependency order:

| Step | Cost | Buys |
|---|---|---|
| Bump the `notes` template version whenever its content changes | one line | Makes the shipped `doctor` check fire at all |
| The template-drift CI gate (§6) | small | Makes that bump impossible to forget |
| `doctor` reports manifest keys the installed template sets that this KB lacks | small | Closes the PDF-glob gap **without** writing to anyone's config |
| ~~`requires_pinakes` + pre-pass read (§4)~~ | small | **Built (G4).** Turns a misleading refusal into an actionable one |
| `pnk upgrade` + `--apply` + `tomlkit` (§5) | medium | Existing KBs actually adopt new defaults |

The remaining three would close the live gap in §3 without touching a user's manifest at all. None is assigned.

# Open corrections after 0.5.0

**Audience: the coder. Goal: executor.** Every item names the file, the current text and the
required text. Nothing here is a judgement call — if an item reads as a question, that is a defect in
this file; say so rather than choosing.

Found by an adversarial review of the 0.5.0 release and of L5c–L8, 20260731. **Done already, do not
repeat:** the GitHub release body now says *"Four, all consequences of the parser change"* with the
non-string-key bullet added; `docs/DESIGN.md`, `docs/MANIFEST.md` and `docs/STATUS.md`'s
release-claim errors are fixed; L5c is closed unbuilt; L6/L7/L8 are revised.

---

## 1 · `src/pinakes/sidecar.py` — the module docstring overstates the fix

**Current** (module docstring, the paragraph about YAML 1.1): claims 1.2 reads the corruption
examples "as the strings they visibly are".

**Required:** three of the four. `0755` becomes int **755** — not the string, and not PyYAML's octal
493 — and survives on disk only because ruamel preserves the source form. The index still stores a
number. `docs/DESIGN.md` already carries the corrected wording; copy it.

**Why it matters:** the same over-generalisation drifted into three files from a decision record
that was right. This is the last instance.

---

## 2 · `CHANGELOG.md` `[0.5.0]` — one break stated twice, and once too broadly

**2a.** The non-string-key refusal appears at `:131` (inside the four-breaking-changes paragraph)
**and again standalone at `:148`**, in two different registers, with `:148` sitting *after* the
"that is a fix, not a break" paragraph. Keep one. `:131` is the right home.

**2b.** `:131`'s wording *"a key that is not a string is refused"* is over-broad. A **uniformly**
non-string-keyed **nested** mapping is accepted and silently coerced (`outer:\n  2: b` →
`{"2": "b"}`); only *mixed* keys and *top-level* keys are refused. `:148` states it correctly — fold
that precision into `:131`.

**Note:** editing a released `[0.5.0]` section directly is correct here. `changelog.d/` is for new
entries; this is a factual correction to shipped text.

---

## 3 · `docs/MANIFEST.md:202` — the `rel` row still says the user writes it

**Current:** `links[].rel` — *"Written by: you"*.
**Required:** credit `pnk link` as `links[].to` already does at `:201`.

L6's Docs line names line ~241 and says an executor updating the field table would not notice it —
this is the field-table row that *also* needs it.

---

## 4 · `docs/STATUS.md:292-294` — the verified-install claim is misleading

**Current:** *"`uv add "pinakes[light]"` works — verified 20260729 01:01 by installing the published
wheel into an empty venv and running `init` → `sync` → `search`."*

**Required:** on a `[light]` install, `pnk init` stamps `provider = "sentence-transformers"` and
`sync` then fails — *"the sentence-transformers backend is not installed"* — until the manifest edit
`README.md:94` documents. Say so, and re-verify against 0.5.0 with a fresh timestamp from `date`.

Predates 0.5.0. **Verify by running it**, not by reading.

---

## 5 · `CLAUDE.md:26` and `docs/STATUS.md:224` — a contents column claims work that shipped in v0.1

**Current:** both 🚫 rows list *link-coverage reporting* among the links release's contents.
**Required:** remove it from the contents column. It shipped in v0.1 (`CHANGELOG.md:1750`, verified
under I9 at `docs/VERIFICATION.md:438`) and `pnk doctor` prints it today.

**Keep the row itself** — the two-cut rule says the links-release *name* stays until L8's final cut.
Only the contents are wrong.

---

## 6 · `plans/links-and-graph.md` — four stale claims in the plan's own frame

**6a. Status header (`:3-5`).** Says *"then passes 1–3 on L5b alone (8, 8, 7 HIGH)"* and *"L1–L8 are
implementable"*. The iteration log records L5b passes 4–7 plus a code review, and L5c is closed
unbuilt. Required: the true pass count, and scope the implementable claim to **L6–L8**.

**6b. Baseline table (`:44-60`).** Says *"Latest release | 0.4.0"* and `main` at `64f210c`, and
*"Re-verify before L1"*. Required: re-baseline at **0.5.0** and current `main`, scoped to L6–L8.

**6c. Verification table (`:1746`).** Names `test_a_non_string_top_level_key_is_refused_with_a_remedy`
and `test_a_single_non_string_key_is_refused_too`. **Neither exists.**
`tests/test_verification.py` hard-fails on an unresolvable row, so this breaks the gate the moment
it is copied into `docs/VERIFICATION.md`. Required: repoint to
`tests/test_sidecar.py::test_a_non_string_key_at_the_top_level_is_refused`.

**6d. Duplicate test names.** L6 names `test_comments_in_the_sidecar_survive_a_rewrite` and
`test_unknown_keys_inside_a_link_entry_survive_a_rewrite`; both **already exist** under L5b
(`tests/test_sidecar.py:470`, `:726`) and are owned by `docs/VERIFICATION.md` rows attributed to L5b.
Required: give L6's CLI-level tests distinct names — suffix `_through_pnk_link` — or the
VERIFICATION rows collide.

---

## 7 · `plans/links-and-graph.md` — the iteration log is out of chronological order

`:1836` (08:00) sits after `:1835` (08:18); `:1828` (05:43) after `:1827` (06:03). Pre-existing.
Sort by timestamp. Low value, do it last.

---

## 8 · `tools/link_density_gate.py` — an uncaught `ValueError` on a non-canonical root

**Current:** `census` calls `document.relative_to(root)` on the **raw** root while `documents_of`
resolves its bases (`(root / name).resolve()`). On macOS, where `/tmp` is a symlink to
`/private/tmp`, the two disagree and the tool dies with a traceback:

```text
ValueError: '/private/tmp/dgtest/docs/access-restrictions.md'
            is not in the subpath of '/tmp/dgtest'
```

Reproduced 20260731 17:16 on `main` with `cp -R tests/demo-kb /tmp/dgtest && uv run python
tools/link_density_gate.py /tmp/dgtest`.

**Required:** resolve the root once, at the top of `census` (`root = root.resolve()`), so the
denominator and the `relative_to` share one base. A test passing a root through a symlinked parent
pins it.

**Why it matters:** it only bites on an explicit non-canonical root, so the committed corpora are
fine and CI is green — but this is the tool L7 tells an executor to run *against a copy* when
comparing the gate's number with doctor's, which is exactly a `/tmp` path on this platform. Found by
a reviewer doing that comparison.

---

## 9 · L6 review 7 — the freshness-branch test never enters the freshness branch

**Blocks the merge.** Everything else in `1d4de4e` is correct: I ran the failure paths end to end
and the gate on that tip (**1034 passed, 0 pyright errors, ruff clean, all gates green**).

**Current:** `test_a_fresh_partner_with_an_unresolvable_path_does_not_crash_the_sync`
(`tests/test_sync_links.py`) asserts only `report.ok`. Its docstring says it covers *"the freshness branch of
`scan()` — which **plain `pnk sync`** takes … No test touched this branch at all"*. It does not
touch it either: the assertion holds whether the branch runs or not.

**Proof** — `is_stale` forced to `return True`, so the fresh branch is never taken:

```text
unmutated:  PROBE link_scan = ()                      1 passed
mutated:    PROBE link_scan = (('partner', 'linked KB `partner` cannot be read at
            ~nosuchuser12345/kb: no such directory.', …),)   1 passed
```

**Required:** add `assert report.link_scan == ()` after `assert report.ok`. That is the
discriminating assertion, and the output above is why: a skipped-fresh row carries no issue, so
`link_scan` is empty **only** when the branch was taken. Confirm by re-running the same mutation —
it must now fail.

**Why it matters:** this is the increment's own recurring class — an assertion satisfied by
something other than the property it names — inside the fix for the finding that said *"that branch
had no test at all"*. The commit message calls the two wrapper removals "mutation-verified"; this
test was not.

**Also verified, so do not re-derive:** `Path.is_file()`, `.is_dir()` and `.exists()` swallow the
`ValueError` an embedded NUL raises (they return `False`), so narrowing `scan_one`'s handler from
`(OSError, RuntimeError)` to `OSError` leaves no escape, and `why_not_a_kb` — which touches only
`exists()` and `is_dir()` — is safe on such a path. `tomllib` does accept `\u0000`, and
`expanduser("~nosuchuser/kb")` does raise `RuntimeError`, both as the commit claims. End to end on
a KB declaring a NUL path and a `~nosuchuser` path: `pnk sync` and `pnk sync --scan-links` both
exit 0 and report each partner as unreachable naming the declared text; `pnk link` through either
alias exits 1 with the same message. The declared-text fallback is pinned at
`tests/test_sync_links.py:543`, so the totality test not pinning it is not a gap.

---

## Not to be fixed — recorded so nobody tries

- **A sidecar carrying its own `%YAML 1.1` directive** is parsed at 1.1, so `country: NO` becomes
  `False`. Frozen in 0.5.0; a `changelog.d/` fragment already records it.
- **An integral `!!float`** keeps its tag and gains quotes on rewrite. Same fragment.
- **A uniformly non-string-keyed nested mapping** is accepted and coerced. A stated residual in
  `docs/MANIFEST.md`'s bounds table, not a defect.
- **The `v0.5.0` tag annotation** says "Three breaking changes". Tag annotations are not cleanly
  rewritable and the tag is published; the release body and CHANGELOG are the corrected records.
- **A raw NUL byte reaches user-facing output** — a `[[links.kb]] path` written as `part\u0000ner`
  produces `cannot be read at part<NUL>ner`, which makes the line binary to `grep` and to any log
  consumer. Reachable only from a hand-written manifest using the `\u0000` escape, never from
  `argv`, which cannot carry one. Sanitising the path into the message would mean every error
  string stops showing exactly what the author wrote — the property review 7 exists to protect.

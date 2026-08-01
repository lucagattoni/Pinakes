## L7 — `pnk doctor`'s link checks (20260801 05:40)

### The check read a partner's index, and DESIGN §6.2 forbids exactly that

**HIGH.** The cross-KB check opened `<partner>/.pinakes/index.db` read-only to ask whether the
target document exists. §6.2 rules that out in the sentence that defines reverse links: they come
from the other KB's committed sidecars, *"**not** its index, which is gitignored and simply absent
in a fresh clone, and which could not be read without holding a second KB's lock"* — repeated
verbatim in `linkscan`'s module docstring, which is the module the check imports from.

`mode=ro` is not enough, and this is the part worth keeping. Measured: a read-only connection still
materialises `index.db-shm` and `index.db-wal` inside the partner's `.pinakes/`, and cannot
checkpoint them away on close. A *diagnostic* command wrote into a KB it was only asked to look at.
Two more consequences fell out of the same choice: a partner cloned but never synced answered
"missing" for every target, and a partner whose `.pinakes/` is mode 0500 degraded silently with an
internal `StoreError` message that misdiagnosed the cause.

The fix is the machinery L2 already had — `partner_sources` + `sidecars_under` + `read_sidecar` —
which is design-conformant, works on a fresh clone with no index at all, and is now tested that way.

**The rule was in the imported module's own docstring.** Not a subtle design point: a paragraph in
the file the new code imports three names from.

### The metric's numerator and denominator came from different populations

**HIGH.** Coverage is `COUNT(DISTINCT src_doc_id) / active`. `sync`'s `SoftDelete` sets
`state = 'deleted'` and drops the chunks — it never deletes that document's `origin = 'sidecar'`
rows. So a deleted document still counted toward the numerator while leaving the denominator,
and the headline number of this increment reported **`2 of 1 documents linked (200%)`**.

A ratio built from two queries is two populations until something makes them one. The join is one
line; noticing it needed one was the work.

### The declared `[[links.kb]] id` is not evidence of which KB is at that path

**MEDIUM.** The check keyed partner document sets on `linked.id` — the *local declaration*.
`linkscan.scan_one` refuses that substitution with `LinkedKbIdMismatchError`, and DESIGN §6.2 rule 1
states it as a rule, because trusting the manifest files another KB's links under this alias.
Measured both ways with a manifest declaring `X` over a partner whose real id is `Y`: a target that
existed in `Y` was reported unresolved, and one that did not was silently resolved.

Two directions need two tests, and only one of them is obvious. Filtering on the declared id also
*skips* a partner whose real id is the one wanted — a dangling target that goes unreported rather
than misreported — and that mutant survived until a test was written for it specifically.

### Four remedies could be blanked with the suite green

**MEDIUM.** The plan required "every new WARN carries a remedy" precisely because the meta-guard
(`test_every_problem_carries_a_remedy`) runs on a fixture where these checks are `OK` and carry no
problem. The helper written to stand in for it asserted `is not None` — which `""` satisfies, while
the guard it substitutes for asserts truthiness. Four of five remedies were emptiable.

**A stand-in for a guard has to assert what the guard asserts.** It now returns the string and each
caller asserts a phrase from it.

### A test named for a guard, authoring nothing that reaches it

**MEDIUM.** `test_an_unreadable_linked_kb_path_is_a_warning_not_a_traceback` was written for the
sentence *"a diagnostic command reporting a traceback is the one outcome `pnk doctor` may not
have"*, and named `why_not_a_kb`'s "third caller needing the same `try`". It authored no cross-KB
link -- so `wanted` was empty, `_unresolved_cross_kb` returned before touching the partner, and the
test pinned the guard in `_linked_kbs` and *neither* of the two in the function the review had just
added. Both are load-bearing: a partner directory behind a mode-0000 parent raises `PermissionError`
out of `partner_sources`, and a `roots` entry carrying an escaped NUL -- which `tomllib` accepts and
`Path.resolve` does not -- raises `ValueError` out of `sidecars_under`.

Third time in two increments that a fixture stopped one step short of its guard, and the shape is
always the same: **the test sets up the failure but not the demand for it.** An unreadable partner
is only reached by code that has a reason to read it.

The dangling-link side of the soft-delete interaction had the same gap in miniature -- the fixture
that proves the *numerator* excludes a deleted document already produced `1 dangling inside this
KB` in the detail it held, and asserted nothing about it. The fix was one line in a test that
already existed.

### Mutants that were not the logic they claimed

**Methodological.** Four "blank the remedy" mutants replaced `"A cross-KB target…"` with
`"" or "A cross-KB target…"`, which evaluates to the original string. All four reported SURVIVED,
which read as four coverage gaps and was really one broken harness. Rebuilt to replace the whole
`remedies.append(...)` call, all four die.

This is the second increment where a mutant that did not reproduce the real prior logic was briefly
taken for a result. The check is cheap: a mutant that survives should be *run* against the case it
claims to break before it is believed.

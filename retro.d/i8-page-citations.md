## I8 — Page citations on both surfaces, and `pnk doctor`'s text yield (20260729 04:55)

**HIGH — `pinakes_get` on a PDF crashed, and no test could have caught it.** `document()` read the
source with `read_text(encoding="utf-8")` inside a `try` guarded by `except OSError`.
`UnicodeDecodeError` is a `ValueError`, so the guard never applied and the traceback escaped through
the MCP surface. It survived since v0.1 because no test ever called `pinakes_get` on a PDF — the
serve suite's KB is two markdown files, and every PDF test lives in a module that never builds a
server. A gap between two test modules is invisible to both.

**HIGH — the plan's `page_start == p` assertion is wrong, and would have failed on correct code.**
The I8 draft specifies that every chunk covering the traced offset "reports `page_start == p`". A
chunk that straddles a page break starts on the *earlier* page, so a word on the later one
legitimately sits inside a chunk whose `page_start` is smaller — which I5 explicitly allows and
which the citation renders as `p1-2`. The trace asserts `page_start <= p <= page_end` instead. The
draft had already corrected "exactly one chunk" to "at least one" for the same fixture; the page
assertion needed the same correction and did not get it.

**MEDIUM — the `stale_extraction` row understated its own gap by half.** DESIGN §4.7's pending
amendment said the marker "today reaches the CLI's `Passage` but stops there", so I8 would carry it
to the agent surface. It reached the CLI's `Passage` *object* and was then dropped by the CLI
renderer too — computed in `search.py`, surfaced nowhere. A field that exists in a dataclass reads,
at review time, like a field that is displayed.

**MEDIUM — the free per-page yield lived inside the only module allowed to import `anthropic`.**
`survey_free_yield` measures what *pypdfium2* got out of a page; nothing about it is paid. But it
sat in `extract/claude.py`, so `pnk doctor` — a free command — could not consume it without
importing the paid path to ask a free question, against CLAUDE.md's own "never probe a backend by
loading it". Moved to `extract/pageyield.py`. The alternative, a second per-page loop in `doctor.py`,
would have been a second definition of a measurement that decides whether to spend money.

**A dead statistic in a shipped template.** The `notes` template's `[budget]` comment told every new
KB that "no shipped code path spends money" — written when that was true, still shipping three
releases later. `docs/GUIDE.md` said the paid extractor was "built but in no release yet". Both are
the same failure as the four README claims found at 0.1.2: prose drifts toward the design, because
the design is what you are thinking about while writing it. Neither was in the increment's scope;
both were found by reading the files the increment touched for other reasons.

**Mutation testing found the test whose name was stronger than its assertion.** Twelve of thirteen
mutations were detected. The survivor deleted `pnk doctor`'s unmeasured-document tally, and
`test_a_swept_cache_entry_is_counted_as_unmeasured_rather_than_as_a_pass` stayed green — because
that test sweeps the *whole* cache and reads a branch that counts documents rather than the tally.
The mixed case, where some documents measure and others do not, is the one the tally exists for, and
it had no test. Its name claimed the general property; its body tested the degenerate one.

### The review pass over I8's own diff

Three defects, all in `pnk doctor`'s new check, all found by reading it adversarially rather than
by any test:

**HIGH — the health check crashed on an unhealthy KB.** `is_paid_backend` raises
`BackendUnknownError` on a name it does not recognise, and the check passed it every PDF's recorded
backend. A KB indexed by a newer pinakes, or with an extra since uninstalled, would make `pnk
doctor` itself raise — the one command someone runs *because* their KB is in a state they do not
understand. §4.4's coherence check has carried the identical guard, with the identical comment,
since I5; the new code was written beside it and did not copy it.

**MEDIUM — a KB whose PDFs are all paid-extracted got a permanent, unclearable warning**, with a
remedy (`pnk sync`) that on those documents *spends money*. The check deliberately skips
paid-extracted documents, then reported the resulting empty measurement through the branch meant
for a swept cache. Skipped-on-purpose and lost look identical to a counter.

**LOW — a single out-of-range page bound was reported as a backwards range.** `page_start=5` on a
two-page document read "pages 5-2 is not a range within it", because the bounds were validated
after the omitted one was defaulted. It describes a range the caller never asked for, and reads as
pinakes' mistake rather than a bad argument. Found by running the tool, not by reading it.

**What the tests could not have caught.** All three needed either a KB state no fixture builds
(an unknown backend name, wholly paid extraction) or a human reading an error message. The
increment's own tests were green throughout, and so was a sixteen-mutation pass — mutation only
perturbs cases somebody already thought of, which is the same limit that let the fragment tooling
ship a duplicate-heading bug at the 0.3.0 release.

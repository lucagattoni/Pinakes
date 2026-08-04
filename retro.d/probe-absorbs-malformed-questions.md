## The reachable-ceiling probe, against a corpus it did not ship with (20260804 04:21)

**HIGH — a measurement tool that absorbs malformed input reports a number that looks valid.** The
finding class, stated once because it generalises past this tool: every defect below is an input
the probe accepted, turned into a plausible verdict, and reported with no mark on the output. That
is strictly worse than a crash. A crash costs an hour; a number that is quietly wrong is read into
`docs/STATUS.md`, decides whether a `schema_version` bump is licensed, and is not falsifiable after
the fact — nobody re-derives a measurement that already looks fine. **Anything that converts input
into a number owes its caller a refusal for input it cannot measure, and the refusal must be a
named failure, never a diagnostic line a reader has to notice.**

The two found by the rehearsal that ran the probe against an external KB — both measured on
demo-kb *under the offline fake backend*, where the corpus reads 18 multi-hop / 9 failing / 3
liftable (the real `[light]` reading of the same corpus is 18 / 1 / 1, so the real-model impact of
each is several times larger):

* **A hop `expect` naming a path not in the index** resolved through a lookup that answered `""`
  for an unknown path, so the hop was recorded `lands=False, reachable=False` — failing and
  unreachable, identical in the output to a genuine one. One typo took `failing` from 9 to 10
  while `liftable` stayed 3. On a 200-document corpus converted by hand from a frozen question
  set, this is not hypothetical.
* **A `multi-hop` question with no `hops`** incremented the denominator and produced no verdict,
  so it could never be counted `failing` and appeared in no other figure: 18 became 19, invisibly.
  The scaffolded template documented `id`, `question`, `expect` and `kind` and **never mentioned
  `hops`** — the trap was armed by our own template, which is why the fix edits both the tool and
  `src/pinakes/templates/notes/eval/questions.yaml`.

**MEDIUM — the first fix was narrower than its own commit message claimed, and an adversarial pass
found three more of the same class.** Worth recording because the pattern is the lesson, not the
individual bugs: a guard written against the two known instances validated *the thing the bug
report named* rather than *the property the measurement needs*.

* **A document with no chunks.** The guard asked whether the path was in `documents`. Every node
  the channel walks is built from the `chunks` table, so a document with zero chunks — a blank
  file, a note that is only front matter, a PDF whose free extraction yielded nothing — passes a
  path check and is still incapable of landing or being reached. It reproduced defect 1 digit for
  digit (`failing` 9 → 10, `liftable` 3), from a path spelled correctly. **"The name resolves" is
  not "the measurement can use it".**
* **A `multi-hop` question with exactly one hop**, which the guard's own wording called "multi-hop
  in name only" and let through. This one is worse than the defect it was written for, because it
  moves `liftable` **upward** (3 → 4). Under-counting fails safe against a floor; over-counting
  licenses the schema bump. A guard on a threshold must be written in the direction that can do
  harm, and the harmful direction here was the one nobody had an example of.
* **An empty hop `query`**, absorbed the same way, and **a golden set with no `multi-hop` question
  at all**, whose entirely-zero report is indistinguishable from a measured one.

**MEDIUM — a test can pin a claim it cannot falsify.** `test_the_probe_names_the_kb_it_measured`
ran only `--fake`, and `--fake` measures a copy of the demo KB: every assertion in it was satisfied
by a probe that ignored `--kb` and hardcoded the demo path, which is the very defect the test
names. It now runs a real `--kb` against a KB deliberately not called `demo-kb` (a small runner
script registers the fake backend in the subprocess), and asserts the recorded root is absolute and
resolved — a relative `--kb` recorded verbatim would label two corpora identically again from two
working directories. **A test whose fixture is the default cannot detect "always reports the
default".**

**MEDIUM — quoting a number without its backend.** The first commit message and changelog fragment
said "measured on demo-kb: `failing` 9 → 10" without saying the numbers were the hashing fake's;
this repository's own retrospective already records that the fake and the real models disagree
about the shape of that answer, and the real reading is 18 / 1 / 1. A user-facing fragment reads as
the real measurement. **Every measured number carries the configuration that produced it, or it is
a different claim than the one intended.**

**The fix removes the place the defect could live, not just the symptom.** `_doc_id` is gone;
`check_measurable` validates the golden set against the active `documents` rows *and* the chunked
subset up front, and `probe` is handed the resulting map, so an unknown path has exactly one place
it can be handled and that place refuses. Validation runs *before* the backend loads — on a real
run that is a model download, and a run that is going to refuse should refuse in a second.

**Two smaller defects of the same family.** `--fake` silently discarded `--kb`, so
`--kb <corpus> --fake` measured demo-kb and reported its numbers as the corpus's; and neither
output format named the KB, so two runs against two corpora produced artifacts indistinguishable on
inspection — which is exactly what made the discarded `--kb` survivable. The pair belongs together:
a silent substitution is only dangerous because the output is anonymous, and **naming the input in
the artifact is the cheapest defence a measurement tool has.** The closing prose's hardcoded
`>= 7` was the same error in prose form, a claim about one corpus printed under the numbers of
another; the threshold now stays with the corpus's own measurement plan.

**On testing a refusal in a subprocess.** These tests run the probe against a KB whose manifest
names a backend the test subprocess never registered, so a run that got *past* the refusal fails
too — a bare non-zero exit proves nothing. Every refusal test asserts the named message and the
offending id/path, and `test_a_well_formed_golden_set_is_not_refused` is the control that keeps the
message attributable to the question rather than the environment. Two assertions were weak for the
same reason and were tightened: `"hops" in stderr` is contained in *every* refusal's closing
remedy, and `"--fake" in stderr` is satisfied by any argparse error, since the usage line names
both flags.

**One deliberate over-reach, recorded so it can be overruled.** A question-level `expect` naming a
missing document refuses the run although `probe()` never reads `expect` — it measures hops. It
cannot move any figure the probe prints, and refusing hard-stops a corpus whose frozen question set
may not be edited. Kept because a golden set naming a document the index does not hold is broken
for `make eval`, which does read it, and measuring a release precondition against an unchecked
question set is not worth the saved minute — but the refusal now says which of its lines move the
count and which do not, rather than claiming they all do.

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

**MEDIUM — the second review pass found the same hole again, in the key nobody had looked at.**
`question.filters` is applied to the last hop and was never validated. A `tags`, `path_prefix` or
`source_type` the index does not hold makes that hop unable to land whatever the corpus contains.
Measured on demo-kb under the fake backend, against its 9 failing / 3 liftable: one such filter
took `failing` to 10; the same filter across every multi-hop question took the run to **18 failing
/ 0 liftable**, exit 0, unremarked. (The review pass that found it quoted only the second figure
for a single question — checking it is what caught the difference, which is the M5 lesson applied
to the fix's own write-up.) It is the empty-`query` defect wearing a different key, it moves *both*
binding clauses, and `failing` moves upward. Two review passes each found one more instance of a
class the first fix was supposed to have closed, which is the actual lesson: **the guard has to be
written from the list of everything the measurement consumes, not from the list of bugs already
reported.** What `probe()` consumes is now the checklist — `hops`, each hop's `query` and `expect`,
the document behind that path, and `filters`. It is validated through `search`'s own `_filter_sql`
rather than a hand-written copy, so the check cannot drift from the semantics it is checking.

**MEDIUM — a third pass, and the same lesson a third time: the artifact recorded every setting
except the one that moves the number most.** `retrieval.rerank` records the *mode* (`local`), never
the reranker's provider and model — and `lands` is `expect in` the top `final_k` **after**
reranking. Demonstrated by the reviewer on one corpus, one path, one manifest, with only
`[rerank] model` changed: 9 failing / 3 liftable became 18 / 12, and every identifying field in the
two artifacts compared equal. Worse, the commit that added the block claimed it mirrored
`eval.py::_header` — which carries *three* blocks, `embedding`, `rerank` and `retrieval`, its
docstring saying it holds "every setting that can move a row". The copy took two of the three and
dropped precisely the one not derivable from the others. **When you cite a prior art as the
standard you met, diff against it.** `index_built_at` joined the payload at the same time: a corpus
edited since its last `pnk sync` is measured as it stood then, and nothing else would say so.

**LOW, and the most human of the findings: one defect, two accusations.** The filters check ran
before the hop-path check, and filters cannot admit a path the index does not hold — so a mistyped
`expect` under a healthy `filters:` block produced two problems, the first of them pointing at the
wrong line, and a `{len(problems)}` count that overstated. Ordering between checks is part of a
refusal's correctness, not a detail: the message that names the wrong cause costs the same debugging
hour the guard was written to save.

**LOW — a sentence assembled from parts is a sentence nobody read.** The per-kind wording was
spliced mid-clause into three messages, and on the branch no test covered — a non-`multi-hop`
question carrying hops, which `load_questions` allows — it rendered "so this probe never measures
this question — only `multi-hop` — so no figure moves for the query rather than for the corpus —
the same silent deflation as a mistyped path": two `so`s, and a closing clause asserting the
deflation the same sentence had just denied. The commit message claimed that wording was fixed; no
test exercised it. Each message now ends with a whole sentence, and a test covers the branch.

**MEDIUM — a test can pin a claim it cannot falsify.** `test_the_probe_names_the_kb_it_measured`
ran only `--fake`, and `--fake` measures a copy of the demo KB: every assertion in it was satisfied
by a probe that ignored `--kb` and hardcoded the demo path, which is the very defect the test
names. It now runs a real `--kb` against a KB deliberately not called `demo-kb` (a small runner
script registers the fake backend in the subprocess). **A test whose fixture is the default cannot
detect "always reports the default".**

The same mistake then repeated one layer down, and is worth recording because it is so easy to
miss twice: the replacement asserted that `kb_root` is *resolved*, using `tmp_path` — which is
already absolute and already resolved, so dropping the `.resolve()` left the entire suite green.
An assertion whose fixture already satisfies the property tests nothing. It now also runs with a
**relative** `--kb` from the corpus's own parent directory, which is the only shape that can fail.

**MEDIUM — naming the corpus is not naming the measurement.** The artifact recorded which KB was
measured and not what produced the numbers. `failing` is `hop.expect in` the top `final_k`
passages, downstream of `candidates_per_source`, `fusion`, `fusion_top_k`, `rerank` and
`vector_tier` — all per-KB manifest keys. Two artifacts from two configurations of the *same*
corpus were indistinguishable, the exact defect the KB-naming fix was written to close, one level
in. `eval.py`'s artifact header already recorded the same set for the same reason; this one now
does too.

**MEDIUM — quoting a number without its backend.** The first commit message and changelog fragment
said "measured on demo-kb: `failing` 9 → 10" without saying the numbers were the hashing fake's;
this repository's own retrospective already records that the fake and the real models disagree
about the shape of that answer, and the real reading is 18 / 1 / 1. A user-facing fragment reads as
the real measurement. **Every measured number carries the configuration that produced it, or it is
a different claim than the one intended.**

**MEDIUM — four passes, and the identity question kept moving outward one input at a time.** Pass
one: the artifact did not name the corpus. Pass three: it named the corpus but not the pipeline.
Pass four: it named corpus and pipeline but not the **golden set** — the input every printed figure
is computed *from*, and the one this branch's own refuse-edit-re-run loop changes most often.
Demonstrated on one corpus, one index, one manifest, rewriting only the hop queries into a generic
word: 9 failing / 3 liftable became 18 / 9, and every recorded field except `reports` compared
equal. The payload now carries the golden set's resolved path, a sha256 of its bytes and its
counts, plus `revision` on both model blocks — a revision selects weights as surely as a model name
does. One correction the sixth pass earned: that "needs no re-sync, so nothing else would move with
it" is true of `[rerank] revision`, which nothing compares against the index, and **false** of
`[embedding] revision`, which `search.check_coherence` guards — change it without a re-sync and the
run stops rather than drifting. Both are recorded; only one of them could ever have moved a figure
in silence. **The general form: an artifact
must identify every input its numbers are a function of, and the way to find them is to enumerate
the function's arguments, not to wait for a reviewer to name one.**

**LOW — the contradiction moved instead of leaving.** The per-kind wording was fixed once by
appending the conditional sentence to the end, which left "the hop is recorded
failing-and-unreachable. No figure this probe prints moves" — an assertion and its denial, one
sentence apart, in a message the previous commit claimed to have fixed. The consequence is now
*entirely* inside the conditional (`_consequence`), so a non-`multi-hop` question is told nothing
was recorded at all, and the test asserts the class ("no line may claim a hop was recorded")
instead of one superseded string.

**LOW — one more absorption, found by asking what `check_measurable` does not compare.** Every hop
was validated on its own and never against its siblings, so two byte-identical hops passed:
`MIN_HOPS` satisfied, one retrieval written twice, and `liftable` moved from 3 to 4 on demo-kb —
upward again. A YAML copy-paste is the realistic route.

**MEDIUM — five passes, and the fixture-satisfied assertion came back twice in one commit.** The
pass-four commit added the golden set to the artifact and asserted it only under `--fake` — where
the measured golden set *is* demo-kb's, so hardcoding the demo path and digest passed every
assertion and the full suite. That is the identical defect pass two found for `kb_root`, recorded
in this very fragment as "a test whose fixture is the default cannot detect 'always reports the
default'", reintroduced by the same author two commits later for the input he had just added. The
same commit pinned `revision` on both model blocks against `manifest.<section>.revision` — and
demo-kb declares neither, so both assertions were `None == None`. **Writing the lesson down does
not apply it: the check is mechanical — for every assertion, ask what value the fixture already
has, and whether a hardcoded constant would pass.** `_fake_kb` now writes distinctive revisions
into its copy, and the golden-set identity is pinned on the real-`--kb` run.

**LOW — one more absorption, one normalisation short.** The identical-hops check compared
`(query, expect)` byte-exactly, so upper-casing or padding the duplicated query defeated it while
the retrieval stayed identical — FTS5 folds case, every backend here splits on whitespace. Measured
on demo-kb: `liftable` 3 → 4, exit 0, the same upward move the check was written to stop. The
fingerprint is now case-folded and whitespace-collapsed. **A guard on "the same input" must
normalise the way the consumer normalises**, which is the `_filter_sql` lesson again in a smaller
key.

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

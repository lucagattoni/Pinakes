## The reachable-ceiling probe, against a corpus it did not ship with (20260804 04:21)

**HIGH — a measurement tool that absorbs malformed input reports a number that looks valid.** The
finding class, stated once because it generalises past this tool: every defect below is an input
the probe accepted, turned into a plausible verdict, and reported with no mark on the output. That
is strictly worse than a crash. A crash costs an hour; a number that is quietly wrong is read into
`docs/STATUS.md`, decides whether a `schema_version` bump is licensed, and is not falsifiable after
the fact — nobody re-derives a measurement that already looks fine. **Anything that converts input
into a number owes its caller a refusal for input it cannot measure, and the refusal must be a
named failure, never a diagnostic line a reader has to notice.**

The two absorptions, both found by a rehearsal that ran the probe against an external KB rather
than `tests/demo-kb`, and both measured on demo-kb before being fixed:

* **A hop `expect` naming a path not in the index** resolved through a lookup that answered `""`
  for an unknown path, so the hop was recorded `lands=False, reachable=False` — failing and
  unreachable, identical in the output to a genuine one. One typo took `failing` from 9 to 10
  while `liftable` stayed 3: the ratio the precondition binds on fell from 3/9 to 3/10 for a
  spelling mistake. On a 200-document corpus, converted by hand from a frozen question set, this
  is not a hypothetical.
* **A `multi-hop` question with no `hops`** incremented the `multi-hop` denominator and produced
  no verdict, so it could never be counted `failing` and appeared in no other figure: 18 became
  19, and the padding was invisible. The scaffolded template documented `id`, `question`, `expect`
  and `kind` and **never mentioned `hops`** — the trap was armed by our own template, which is why
  the fix edits both the tool and `src/pinakes/templates/notes/eval/questions.yaml`.

**The fix removes the place the defect could live, not just the symptom.** `_doc_id` is gone;
`check_measurable` validates every `expect` in the golden set against the active `documents` rows
up front, and `probe` is handed the resulting map, so an unknown path has exactly one place it can
be handled and that place refuses. Validation runs *before* the backend loads — on a real run that
is a model download, and a run that is going to refuse should refuse in a second.

**Two smaller defects of the same family.** `--fake` silently discarded `--kb`, so
`--kb <corpus> --fake` measured demo-kb and reported its numbers as the corpus's; and neither
output format named the KB, so two runs against two corpora produced artifacts indistinguishable
on inspection — which is exactly what made the discarded `--kb` survivable. The pair is worth
recording together: a silent substitution is only dangerous because the output is anonymous, and
**naming the input in the artifact is the cheapest defence a measurement tool has.** The closing
prose's hardcoded `>= 7` was the same error in prose form, a claim about one corpus printed under
the numbers of another; it now points at the corpus's own measurement plan for the threshold.

**On testing a refusal in a subprocess.** These tests run the probe against a KB whose manifest
names a backend the test subprocess never registered, so a run that got *past* the refusal fails
too — a bare non-zero exit proves nothing. Every refusal test asserts the named message and the
offending id/path, and `test_a_well_formed_golden_set_is_not_refused` is the control that keeps the
message attributable to the question rather than the environment. Mutation-verified per assertion:
restoring the `""` lookup failed only
`test_the_probe_refuses_a_hop_expecting_a_document_the_index_does_not_hold`, at
`assert REFUSAL in completed.stderr`, with `returncode != 0` still passing for the wrong reason —
which is the whole argument for asserting on the message.

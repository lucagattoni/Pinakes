## T2 — Reporting template drift as a diff (20260807 22:28)

**HIGH — A test that never calls the function under test cannot kill a mutant inside it.**
`test_the_kb_identity_block_never_produces_a_hunk` was written for the mutant the plan called the
one that matters: rendering the old side with the KB's recorded reference and the new side with the
*installed* one, which is what a reader of `init.py:75` would naturally write, and which puts a
`[kb]` hunk in every report on every KB. The test asserted exactly that property — by rendering
both versions itself. So the mutant went into `doctor._template`, the test rendered its own two
sides correctly, and it passed. The property was right, the altitude was wrong. It now also asserts
the count `doctor` reports, against a synthetic pair that differs on one line: correct is two, a
leaking identity block is four.

**HIGH — A line-count assertion is blind to an edit that substitutes rather than adds.** The
invariance test edits the user's manifest and asserts the reported count does not move, which is
what catches a report built from `pinakes.toml` instead of from two archived templates. With that
defect injected, replacing `fake-model` with `fastembed-model` and `final_k = 5` with
`final_k = 4` left the count *identical* — one line replaced by another is still one line on each
side of a diff. The test was invariant under the implementation it existed to reject. Appending a
comment line fixes it, because no substitution can absorb an added line.

Both were found by running the mutation pass, not by reading the tests. Two of five mutants
survived a suite that was green, and neither survivor was a bug in the increment.

**MEDIUM — A comparison that reads one of four files must not report `0`.** A template version
denotes four consumed files; this check diffs `pinakes.toml.j2`. A bump touching only
`eval/questions.yaml` renders two identical manifests, and the first implementation said
*0 lines differ* — true of the manifest, read as *nothing changed*. It is not a hypothetical: of
the ten commits between the `notes` template's first version and its second, five touched the
golden set and none touched the manifest. It now says *same manifest* and names what a version
covers beyond it.

**MEDIUM — The most-read string promised something no release can deliver.** The *cannot compare*
remedy ended "from the next template version onward the comparison is automatic". Under D-2b
`notes@1.0` is deliberately unarchived, so a KB recording it stays uncomparable however many
versions ship after — the sentence was false for precisely the readers who see it most, which is
every KB in existence. What a later version changes is the *next* KB, and the remedy now says that
and says the missing content is gone rather than pending.

**A second copy of "the variables this build supplies" was one commit from existing.**
`tools/template_drift_gate.py` leg (vi) asserts every archived version renders, under a context
written out in the gate. The product now renders both sides of a comparison under
`template.render_context`. Two literals, and the failure mode is the gate staying green while
`pnk doctor` raises on the KB in front of it — the gate would have been asserting that the archive
renders under a context nothing uses. The gate now builds its keys from `template.CONTEXT_KEYS`,
and `test_render_context_supplies_exactly_the_declared_union` pins the remaining seam.

## The heading-coverage check — two findings, one of them about my own test

**HIGH — the open correction's diagnosis was approximately right and precisely wrong, and the
difference decides the fix.** Item 1 read *"the heading grammar is Markdown-shaped; RFC section
numbering is not, so nothing matches and the strategy quietly becomes size-based"*. That describes a
regex being tried and failing. What actually happens is `chunk.py:131`:

```python
blocks = _markdown_blocks(text) if kind == "markdown" else _plain_blocks(text)
```

`_markdown_blocks` is **never called** for a `.txt` file, and `_plain_blocks` sets
`heading_path=None` unconditionally. Nothing failed to match because nothing was tried. The
consequence for the fix is not cosmetic: tightening or extending a regex would have changed nothing,
and the real change is adding heading detection to a code path that has none. It also bounds the
blast radius in the useful direction — `tests/demo-kb` is Markdown, so a plain-text grammar cannot
move the golden set, and *"changing chunking needs eval justification"* becomes a thing you can
prove rather than argue.

**A measurement replaced a threshold.** Chunking the committed corpora directly — no index, no
embeddings, `chunk_document` called in a loop — gave demo-kb 60/60 and partner-kb 55/55 at 100%
against the RFC corpus's 0%. Bimodal, so the predicate can be *"zero for this source type"* and the
check carries no constant anybody had to calibrate. The alternative, a fitted percentage floor,
would have needed a corpus to fit against and would have fired on ordinary documents whose opening
paragraph precedes their first heading.

**MEDIUM — mutation testing refuted one of my own tests within a minute of writing it.** I wrote
`test_heading_coverage_counts_only_active_documents`, asserting the `state = 'active'` filter. M1
deleted the filter and the test **stayed green**. The reason is that `SoftDelete` drops a document's
chunks as well as flipping its state, so a chunk-counting query has nothing to over-count either
way — unlike `_links`, which counts *documents* and genuinely needs the filter it records having
shipped without (`2 of 1 documents linked (200%)`).

The test was kept and **renamed to what it proves** (`test_a_removed_documents_chunks_stop_being_counted`),
with the refutation written into its docstring so nobody re-derives the wrong claim from the old
name. The filter stays as defensive consistency with `_links`, marked as unreachable by this
fixture rather than presented as guarded.

This is the file's own recurring failure class caught in the act: **an assertion satisfied by
something other than the property it names.** Three of the four mutants died as intended (the
zero-per-type predicate, the two-cause remedy split, the WARN status); the one that survived was the
one whose name made the strongest claim. Green proved the test ran; only the mutant proved what it
could detect — and for one of five, the answer was "not the thing in its name".

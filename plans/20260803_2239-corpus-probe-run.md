# The probe run against the RFC corpus — conversion contract and procedure

**Audience: the agent that will run the measurement. Goal: executor.** Written 20260803 22:42,
while the corpus was still being built, precisely so that this step would not be improvised after
it lands. This is the second measurement of the graph release's precondition — the first, on
`tests/demo-kb`, failed for corpus reasons
([`docs/STATUS.md`](../docs/STATUS.md#can-the-graph-releases-gate-be-reached--measured-20260801-1214))
— and its honesty rests on a separation this file exists to enforce.

**You are not the corpus author.** The corpus and its frozen question set were built by an agent
that had never seen the probe, does not know the passing thresholds, and recorded the freezing
commit sha in its report. You measure; you do not author. If at any point the honest move seems to
be "improve a question", stop — that is the circularity decision 14 removed, and it is
undetectable after the fact.

## The gap this file closes

The frozen questions live in the corpus repo as **plain data** —
`eval/multihop-questions.yaml`: `id`, `question`, `evidence` (2+ document filenames), `why` — by
design: the author was barred from reading pinakes internals, so it could not have written the
eval schema. The probe reads `<kb>/eval/questions.yaml` in the **`Question` schema**:
`id`, `question`, `kind: multi-hop`, `expect`, scripted `hops` (each hop a `query` + `expect`).
Someone must convert, and conversion touches frozen material. These are the rules.

## Conversion rules — mechanical, reviewable, and biased against yourself

1. **The frozen file is never edited.** The conversion writes a NEW file,
   `eval/questions.yaml`, in the corpus repo, committed with a message naming the freezing sha it
   was derived from. Both files stay committed; a reviewer must be able to diff intent against
   translation.
2. **`id` carries over unchanged.** One frozen question → one converted question. None dropped,
   none added, none merged — the converted file has exactly as many `multi-hop` entries as the
   frozen file, and the count is stated in the run report.
3. **`question` is copied verbatim.** Not clarified, not disambiguated, not shortened.
4. **`expect` is the frozen `evidence` list, verbatim** (translated to the corpus's document
   paths). Every listed document, only the listed documents.
5. **Hop queries are extracted, never invented.** Each hop's `query` must be a substring or a
   direct clause-for-clause restatement of the frozen `question` text — the part of the question
   that asks for that hop's document. If a hop's query cannot be written without adding
   information the question does not contain (a document title, a term of art from the target
   document, vocabulary the author did not use), **write the weaker query the question supports**.
   The conversion must make questions *no easier* than the author wrote them: when in doubt,
   under-specify the hop.
6. **Ambiguity is reported, not resolved.** A frozen question whose hop structure is genuinely
   unclear (which evidence document is hop 1?) is converted with hops in the order the evidence
   list gives, and flagged in the run report. It is not reworded and not dropped.
7. **The planner reviews the conversion diff before the probe runs** — frozen file beside
   converted file, rule by rule. The probe does not run until that review is on record.

## The run

Preconditions: the corpus repo cloned clean at its frozen sha; `pinakes` at the current release
from PyPI, `[light]`; the corpus synced (`pnk sync`) at the current `schema_version`. Then, from
the pinakes repo:

```bash
uv run python3 tools/reachable_ceiling_probe.py --kb <corpus-path> --json
uv run python3 tools/reachable_ceiling_probe.py --kb <corpus-path> --drop co-located
uv run python3 tools/reachable_ceiling_probe.py --kb <corpus-path> --drop shared-tag
```

**The probe must be shown to fail on THIS corpus** — the `--drop` runs are that proof, per corpus,
not inherited from demo-kb: if removing an edge kind does not move the reachable count here, the
probe is measuring something other than this corpus's edge set and the main number means nothing.
The RFC corpus has real directories and real tags, so **both** drops must move the count (demo-kb
could only exercise `co-located`).

## What is reported — all of it, whichever way it points

The same table shape as
[the first measurement](../docs/STATUS.md#can-the-graph-releases-gate-be-reached--measured-20260801-1214):

| | Required | Measured |
|---|---|---|
| multi-hop questions failing today | ≥ 7 | ? |
| of those, reachable within 2 logical hops, **without** authored edges | ≥ 7 | ? |
| with authored edges (recorded, licenses nothing) | — | ? |
| at-seed share of "reachable" | — | ? |

Plus: the per-question outcomes, the `--drop` deltas, and the conversion flags from rule 6. The
**without**-authored figure is the only one that binds (G2 trap 2). The at-seed share is reported
because a "reachable" question that traversed no edge is ranking headroom, not channel headroom —
the first measurement found two of three such.

**Both outcomes are publishable.** Precondition met → the planner brings the G3 restart decision
to the user. Precondition failed on a corpus with real structure, real links and real prose → the
honest reading is that the expansion channel is not worth a `schema_version` bump, and the graph
release closes with that finding. Failing twice is a result, not a failure of the measurement.

## What this run must not do

- Edit, drop or add questions after seeing any probe output — rules 1–6 all end at the freeze.
- Tune the corpus (buckets, tags, links) toward a number. The corpus repo is frozen for the run.
- Report one reachability figure. Two, always, and the at-seed share.
- Start G3 on its own authority. The measurement is evidence; the decision is the planner's to
  bring to the user, either way.

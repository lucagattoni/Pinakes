# Retrospective fragments

One file per increment's retrospective, spliced into `docs/RETROSPECTIVES.md` at release time by
`python3 tools/fragments.py --stream retrospectives --apply`.

Same reason as [`changelog.d/`](../changelog.d/README.md): every increment writes to this document,
so it is one of the two files most likely to be edited twice in an hour.

## Naming

    retro.d/YYYYMMDD_HHMM-<slug>.md

`YYYYMMDD_HHMM` is when the fragment was written, **UTC** — **read the clock, never compose it**
(`date -u "+%Y%m%d_%H%M"`). Fragments written before 20260804 11:32 carry a local time and keep it.
Same prefix as `changelog.d/`, plans and branches; `tools/fragments.py`
strips it before reading the slug.

The slug is lowercase-with-hyphens, with no category prefix — a retrospective is free-form prose
rather than one of a fixed vocabulary. Name it for the increment:
`retro.d/20260729_0336-i7d-recorded-fixtures.md`.

## Contents

The whole section, including its own `##` heading with the timestamp the file's own rules require:

    ## I7d — Recording the fixtures (20260729 03:36)

    **HIGH — …**

Fragments are spliced **before** the design-review-passes section, which stays at the foot.

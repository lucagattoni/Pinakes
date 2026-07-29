# Retrospective fragments

One file per increment's retrospective, spliced into `docs/RETROSPECTIVES.md` at release time by
`python3 tools/fragments.py --stream retrospectives --apply`.

Same reason as [`changelog.d/`](../changelog.d/README.md): every increment writes to this document,
so it is one of the two files most likely to be edited twice in an hour.

## Naming

    retro.d/<slug>.md

Lowercase-with-hyphens; no category prefix, because a retrospective is free-form prose rather than
one of a fixed vocabulary. Name it for the increment: `retro.d/i7d-recorded-fixtures.md`.

## Contents

The whole section, including its own `##` heading with the timestamp the file's own rules require:

    ## I7d — Recording the fixtures (20260729 03:36)

    **HIGH — …**

Fragments are spliced **before** the design-review-passes section, which stays at the foot.

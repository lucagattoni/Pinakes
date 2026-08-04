# Changelog fragments

One file per change, spliced into `CHANGELOG.md` at release time by
`python3 tools/fragments.py --stream changelog --apply`.

**Write a fragment instead of editing `CHANGELOG.md`.** Several agents work in this repo at once,
and `CHANGELOG.md` is the one file every piece of work must touch. Two agents cannot conflict in
separate files, so the conflict class stops existing rather than being managed
(`tools/shared_file_overlap.py` reports the collisions that remain elsewhere).

## Naming

    changelog.d/YYYYMMDD_HHMM-<category>-<slug>.md

`YYYYMMDD_HHMM` is when the fragment was written, **UTC** — **read the clock, never compose it**
(`date -u "+%Y%m%d_%H%M"`). Fragments written before 20260804 11:32 carry a local time and keep it;
converting a recorded timestamp invents precision nobody measured. It orders `ls` chronologically
and dates a fragment without opening it, and
it is the same prefix plans and branches carry. `tools/fragments.py` strips it before reading the
category, so it never becomes part of the slug.

`<category>` is one of Keep a Changelog's six — `added`, `changed`, `deprecated`, `removed`,
`fixed`, `security` — and it lives in the **filename** so it cannot drift from the content.
`<slug>` is lowercase-with-hyphens. `ls changelog.d/` is then a readable summary of everything
unreleased.

    changelog.d/added-record-claude-fixtures.md
    changelog.d/fixed-refusal-reason-discarded.md

## Contents

The entry body only — no `### Added` heading, which the assembler writes from the filename. Write
it exactly as it should read in the changelog, starting with `- **The short claim.**`.

The rule that has not changed: **the fragment lands in the same commit as the code it describes.**

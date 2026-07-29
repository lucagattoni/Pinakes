- **Six claims that 0.3.0 falsified, including one plain factual error about PyPI.**
  `docs/STATUS.md` said *"Published version: **0.2.2 only**"* while 0.3.0 had been on the index for
  three hours — and that row is a fact about PyPI, not about this repo, so nothing in the release
  procedure was ever going to notice. Verified against the index and by installing: 0.2.2 and 0.3.0
  are both published, all four extras (`st`, `light`, `pdf`, `claude`) resolve, `requires-python` is
  `>=3.13`, and `uv add "pinakes[light,pdf]"` into an empty venv gives `pinakes 0.3.0`.

  The others were the release's own shadow:

  - The **naming table** still listed *the paid-extraction release* among "bodies of work that do
    not exist yet". It shipped as 0.3.0. The **roadmap** still had it italicised and unticked,
    directly under three ticked rows.
  - **`README.md`'s install block** offered only `[st]` and `[light]`, so a new reader could not
    discover PDF ingest — the headline capability of the two most recent releases — from the
    quickstart at all.
  - **`README.md` claimed a capability that is not built.** *"Cross-KB answers are capped by how
    well your KBs are linked"* implies cross-KB answers exist; the addressing ships, the traversal
    is the links release. Now says so, and points at the roadmap.
  - **`docs/README.md`** still described `MEASUREMENT-RUN.md` as *"how do I get the numbers this
    project admits it lacks"* and routed to it *"while the numbers are still missing"*. The run
    happened on 20260729 and `STATUS.md` carries its results.
  - **`KB-UPDATES.md`** said *"no increment assigned"* in three places; its `requires_pinakes` half
    is now assigned to G4 in `plans/links-and-graph.md`.

  **`CLAUDE.md` gains the rule**, because the release procedure is where this is preventable: a
  release makes three documents stale the instant it publishes — STATUS's PyPI table, STATUS's
  roadmap, and README's install lines — and they are swept in the release commit, verified by
  querying the index and installing what the docs show rather than by reading them.

- **`CLAUDE.md` is 273 lines down to 191, and two new documents own what left it.** That is still
  above the ~150 guardrail that triggered the extraction: the five sections the deferred note marked
  keep-verbatim (the `land.py` guard, the PUBLIC-repo rules, documentation ownership, naming and
  unbuilt-work naming) are 98 lines on their own, so 150 is unreachable without reopening them. [`docs/BUILDING.md`](docs/BUILDING.md) is the increment procedure (worktree, tests
  in the same increment, `check.sh`, mutation, adversarial review, fragments, `land.py`), the
  executor sibling of `docs/RELEASING.md`; [`docs/INVARIANTS.md`](docs/INVARIANTS.md) is the list of
  contracts that fail *silently* when broken. **INVARIANTS is an index, not a copy:** measured before
  the move, eight of the nine invariants were already owned by `DESIGN.md`, `MANIFEST.md`,
  `VERIFICATION.md` or `CLI.md`, so each row links its owner and only the five implementation rules
  nothing else states — the `ruamel`-not-`pyyaml` rule, the two `docs/` exceptions, what a `void`
  record needs, never probing a backend by loading it, and `Decimal(str(value))` — are written out.
  A verbatim move would have created a second copy of eight facts inside the file set whose rule is
  *one fact, one home*.
- **Eight references that named `CLAUDE.md` for content that moved now name its new home** — so no
  pointer outlives what it pointed at. To `docs/INVARIANTS.md`: `docs/DESIGN.md` §1,
  `docs/ROADMAP.md`'s deep-release entry, and `tools/paid_path_gate.py`'s failure message and module
  docstring. To `docs/BUILDING.md`: `README.md`, `docs/ROADMAP.md` § *How this project builds*, and
  `tools/fragments.py`'s docstring. To `docs/README.md` § Conventions:
  `tools/record_claude_fixtures.py`'s `--at` help text, which cited a sentence CLAUDE.md no longer
  carries. **Five of the eight name the file rather than the moved text**, so a grep for the moved
  wording finds none of them — the sweep has to run on the source file's own name.
- **`docs/README.md`'s `plans/` table said the closed links-and-graph plan was "the current build
  order", and never listed the live investigation at all.** Both fixed: the metadata-as-retrieval-
  context plan leads the table, links-and-graph is marked closed with what its G5 gate did and did
  not license, and the table now says outright that most of `plans/` is not live work and that
  `CLAUDE.md` names the two that are.

- **`docs/README.md` still told every increment to write its `[Unreleased]` entry into
  `CHANGELOG.md`** — the edit the fragment convention had just forbidden. `CLAUDE.md` gained
  `changelog.d/` and `retro.d/` in the same change that introduced them, and the routing table that
  `CLAUDE.md`'s own build order defers to ("the docs are built so an increment touches few files")
  was left pointing at the old procedure. Two documents disagreed about a rule that exists to stop
  two agents disagreeing.

  It matters more than a stale line usually would, because nothing catches it: `tools/fragments.py
  --check` validates the fragments that exist and has no opinion about a commit that edited
  `CHANGELOG.md` directly, so an agent following the checklist would have landed the violation
  green.

  The landing checklist now ends in a `changelog.d/` fragment and a `retro.d/` one, the fact-routing
  table says where each of those two documents is *written* as distinct from where it is *read*, and
  the index warns that anything unreleased is still sitting in its fragment directory rather than in
  the document — which is also the answer to why "re-read `RETROSPECTIVES.md` before each increment"
  can quietly miss the newest findings.

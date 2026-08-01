- **`[sources] include` can no longer walk out of the KB, or write files outside it.** `roots`
  already had to stay inside the KB; `include` was validated nowhere, and the walk's containment
  test was `candidate.relative_to(kb_root)` — purely lexical, so `docs/../../outside/x.md` *is*
  relative to the root as a string. Three measured consequences, all fixed: a `..` pattern indexed
  files outside the KB and **minted sidecars beside them**; an absolute pattern came out as a bare
  `NotImplementedError` traceback with no `error:` line and no remedy; and a **symlinked directory**
  inside the KB carried the walk out with no `..` and no absolute path anywhere in the manifest.
  An escaping or absolute pattern is now a `ManifestError` at load, matching the `roots` precedent,
  and the walk re-tests each candidate because no load-time check can see a symlink.

  **This is a behaviour change for a manifest that already carries such a pattern** — which is a
  manifest writing files outside its own KB, so the hard error is the right precedent rather than a
  softened warning. `pinakes.toml` is committed and shared: cloning a KB and running `pnk sync` ran
  *its author's* `include` against *your* tree. A pattern with `..` that lands **inside** the KB
  (`include = ["../notes/*.md"]` from `docs/`) is still accepted — what matters is where the path
  lands, not whether `..` occurs in it. `exclude` is deliberately not validated: a pattern there can
  only fail to match, never widen the walk.
- **A document reached by two legal spellings is one document.** The index key came from
  `relative_to`, which is lexical and hands back the `..` it was given, so `include =
  ["../notes/*.md"]` keyed a file as `docs/../notes/n.md`. With that file also reachable under a
  second root it was indexed once and then **failed twice** — *"appeared after the walk had already
  read this directory"* — because the sidecar found under one key was invisible under the other,
  and the unmatched-files sweep reported an indexed document as unmatched. The key now collapses
  `..` lexically. It is not *resolved*: that would follow a symlinked directory and silently re-key
  every document under it, which for an existing KB is a path change on a permanent identity.
- **`tools/link_density_gate.py` no longer dies on a root reached through a symlinked parent.**
  `census` resolved one of its two bases and not the other, so on macOS — where `/tmp` symlinks to
  `/private/tmp` — running the gate against a copy of a KB exited with a `ValueError` traceback
  instead of a verdict. It is the tool an executor is told to run against a copy.

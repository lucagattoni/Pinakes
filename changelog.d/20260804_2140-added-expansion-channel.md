- **The graph expansion channel — `[retrieval] graph_channel = "off" | "expand"`, default `off`.**
  With `"expand"`, the fused top-*k* of the retrieval pipeline become roots, the structural edge
  set is walked outward to depth ≤ 2 **logical hops**, and what it reaches is ranked and handed to
  reciprocal rank fusion as a **third** input. Chunk neighbours rank by cosine against the query;
  a doc, tag, heading or directory node carries no content embedding, so it passes through by edge
  weight and contributes its member chunks, which are then ranked like any others. `adjacent_k`
  caps every node's expansion, after ranking, and a hub expands **once globally** — a popular tag
  is walked once per query rather than once per encounter.

  **Off, nothing runs** — no query reaches `nodes` or `edges`, and a test counts the statements
  that do. **On over an empty edge set, the result is today's two-list fusion exactly**: RRF sums
  one reciprocal-rank term per ranking, so an empty third ranking contributes no term to any score
  and no key to the result. Arithmetic identity, not approximation.

  **Same-document chunks reachable only through their own document's membership edge are
  excluded** — from the output *and* from the fan-out budget. Intra-document structure is what
  `sibling`, `parent-child` and `in-section` are for. A same-document chunk that is *also* a
  sibling, a child or a section-mate is returned: the "only" is load-bearing, and both halves are
  pinned by tests.

  **A root is dropped before the fan-out cut for the same reason.** It is already in the list the
  channel is a third input to, so it is expanded and never emitted — and the neighbours of a fused
  top-*k* chunk are very often other fused top-*k* chunks, so leaving it in the cut spends slots on
  rows guaranteed to be discarded. `adjacent_k` therefore counts only candidates that can actually
  reach the output.

  **Nothing on a released surface changes.** `pnk links` and `pinakes_links` return exactly what
  they returned in the links release — their `--json` output on both committed corpora is compared
  byte-for-byte, **with the channel on**, against the fixture captured before the schema bump.

  **`graph_channel` is not stamped into the template**, for the same reason as `adjacent_k`: an
  unknown key is a hard error, so a manifest carrying it cannot be read by any Pinakes released
  before it existed. `"ppr"` is not an accepted value — a manifest that can name a mode the code
  does not implement is a setting that silently does nothing.

- **`tools/graph_gate.py` — the golden-set gate that decides the default, computed rather than
  argued.** It reads three per-question artifacts — `off`, `expand` without authored edges, and
  `expand` with them, all measured at the same HEAD against one index — and prints the counts, both
  p-values and a clause-by-clause verdict: an exact one-sided sign test on the discordant questions
  of the `multi-hop` class, no class regressing beyond `compare()`'s tolerance, `false_abstain`
  decomposed so that newly-found questions reported at low confidence do not veto the win, and no
  other regression a re-baseline could absorb. **Both edge-set variants must reach p < 0.05 and the
  more conservative licenses**; a leg is identified by its artifact header rather than its
  filename, so a `--before` produced with the channel already on is refused instead of silently
  comparing a configuration against itself.

- **`tools/graph_matrix.py` — the eval matrix, reported beside the headline.** Seven legs over one
  index with no re-sync: the three the gate reads, the `--drop sibling` and `--drop parent-child`
  arms, and APPROACH §4A's two ranking knobs (in-degree salience, the link-distance term). It also
  reports, per improved question, **which edge kind carried the lifting path** — the only thing in
  the output that can tell a result carried by `shared-tag` and `co-located` over a vocabulary and
  a directory layout the corpus author chose from one carried by `sibling` or `in-section`.

- **Per-question eval artifacts now record `graph_channel` and the edge-set variant**, and
  `python -m pinakes.eval` takes a repeatable `--drop KIND`. Without both in the header, the gate's
  three legs are indistinguishable on inspection.

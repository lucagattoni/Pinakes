- **[`plans/links-and-graph.md`](plans/links-and-graph.md) revised after a fourth adversarial pass —
  13 HIGH, down from 24, and the first pass with no self-refuting fix.** Five findings collapsed
  into one decision: **the traversal surface serves documents only.** Tag, directory, heading and
  chunk nodes have no `doc_id` and cannot be expressed in the neighbour shape the plan pins with a
  test, so they stay internal to the expansion channel permanently. That makes the structural-edge
  increment genuinely inert rather than aspirationally so, removes a released-payload change nobody
  owned, and deletes a filter-flip whose conditionality was undecided in a way that broke either
  reading.

  **Cross-KB traversal is one hop, and the plan now says so.** KB *K*'s `links` table holds its own
  outbound rows and its inbound ones, never a third KB's outbound rows — so a depth-2 hop *through*
  a cross-KB neighbour has nothing to walk without opening that KB's index, which DESIGN §6.2
  forbids. The Goal had been claiming more than the data model can deliver; a cross-KB neighbour is
  now terminal at any depth, and `frontier` says so rather than leaving a caller to retry a hop that
  can never succeed.

  Also closed:

  - **`frontier` was contract text with no owner and no definition** — half of the pair the research
    says an agent's loop consumes. It belongs to the pure core, and an entry now carries *why* it
    was not expanded: `depth`, `fanout`, `rows`/`tokens`, or `terminal`. A caller that cannot tell
    `fanout` from `terminal` retries forever.
  - **The channel's gate conflicted with `compare()`, which is a hard CI gate.** Five misses
    becoming hits, two at low confidence, is 0.030 against a 0.02 tolerance — CI red on a channel
    the gate had just blessed. Turning the channel on now re-baselines in the same commit, with the
    rise decomposed so that only *lost* confidence counts as a regression.
  - **The go/no-go for the graph release measured the wrong quantity.** It counted questions that
    currently fail, but a question can only be lifted if its evidence is reachable in the edge set —
    and with `mentions` cut, the authoring rule ("evidence split across two documents with no shared
    vocabulary") actively selects for pairs the remaining edges cannot bridge. The research's own
    channel-reachable ceiling comes back as an in-memory probe that needs no schema change, so the
    decision happens **before** every KB in existence is forced to rebuild.
  - **The node identity scheme spanned five incompatible id spaces** and was never written down —
    including a chunk key that would have used the rowid the storage layer documents as having no
    identity across rebuilds. Specified, with an orientation rule, because a `src`-only damping
    query silently drops half of every symmetric relation.
  - **The graph release now has a stated fallback**: if the precondition fails, the three increments
    that do not depend on structural edges ship on their own rather than stranding finished work.

- **`pinakes_links` on the MCP surface** (L5 of the links release) — the same traversal `pnk links`
  performs, for the agent this project calls its primary caller. `depth` is capped at 3 server-side
  and there is no query language, ever; `score` and `frontier` come back on every call, not only
  when something interesting happened. **`confidence` is always `unknown`**: the signal is
  calibrated per KB on the reranker score of a retrieved *passage*, a traversal neighbour is not
  one, and a list spanning two KBs has no single manifest whose thresholds apply — reporting
  low/medium/high would be an invented signal. A neighbour in a KB **this server was not pointed
  at** is returned with `reachable: false`, its ids and a reason, because omitting it would hide a
  link that exists; reachability is a property of the server invocation, not of a manifest. The
  free-path gate's MCP handshake now **calls** the tool rather than only listing it — listing walks
  signatures and docstrings, so a tool whose body imported a paid client would have listed
  perfectly and never been seen.
- **One traversal projection, shared by `pnk links --json` and `pinakes_links`**
  (`pinakes.graph.present`). The two answered the same question through two hand-written copies of
  the same dict literals and had already drifted — the MCP `frontier` carried a `distance` the CLI's
  did not, `scored_by_query` reached only one of them, and `unresolved` dropped the `kb_id` its
  sibling lists carried. Nothing failed, because nothing compared them. **`direction` is now keyed
  by `(node, rel)` rather than by node**: given `a --related--> b` and `b --cites--> a`, asking about
  `a` reported the citation as running *from* `a` — backwards, on both surfaces, since L4. One
  relation written from both ends now reads `both`. **An unrecognised `direction` is refused**
  (`TraversalError`) instead of running neither query and returning a confident empty answer;
  `DIRECTIONS` had been defined and never enforced, and only `argparse` was catching it on the CLI.
  **An empty answer now says whether your own arguments emptied it** — `direction="out"` on a
  document whose only link is inbound used to advise "No links from here, search instead", which
  tells an agent to stop traversing a graph it is standing in.
- **A neighbour's `direction` no longer changes with `depth`.** The `both` merge is decided inside
  one expansion and never across them: direction is relative to the node being expanded, so an edge
  found while expanding an unrelated parent was rewriting a row already returned from the start
  document. `pnk links` prints `<->` for a relation written from both ends. An unknown `direction`
  is now refused *before* a query loads the embedding backend, rather than after cosining the whole
  KB to answer a call that could never succeed. And a document whose links all point at documents
  the KB no longer has is no longer told it has no links — the payload was listing them under
  `unresolved` in the same breath — on both surfaces, and worded without a direction, because a
  deleted document keeps its outbound `links` rows and "this document's links point at…" would
  then credit a link to whichever end did not write it. When the caller also narrowed the walk,
  the narrowing is reported first: a live neighbour may sit one dropped argument away, and sending
  them to full-text search instead is the worse of the two wrong answers. `pnk links` says the same
  three things in the same order, so a person and an agent get the same account of an empty walk.

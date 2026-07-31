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

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

`pnk doctor` reports link coverage as the **ratio** DESIGN §6.2 promises — `8 of 30 documents
linked (27%)` — rather than an edge count, and resolves cross-KB targets instead of declaring them
unchecked. A target whose own KB is on this machine and does not have the document is now a WARN
with a count; one whose KB is *not* here is counted and left alone, because an index that cannot
see a KB has no standing to call its documents missing.

A new **linked KBs** check reads `[[links.kb]]` from the manifest alone, so it runs on a freshly
cloned KB with no index — which is exactly when a committed absolute `path` matters. Four outcomes:
a path that names no path at all, a KB absent from this machine, an absolute path (warned even when
it resolves, because it publishes one machine's layout), and everything fine.

A KB where nothing links to anything is now a WARN nudge rather than a silent OK.

- **The structural node model and edge set (`schema_version` 3).** `pnk sync` now derives a
  heterogeneous graph into two new index tables, `nodes` and `edges`. Five node kinds —
  **chunk**, **document**, **tag**, **heading-path** (scoped per document) and **directory** — and
  six derived edge kinds: `membership`, `sibling`, `parent-child`, `in-section`, `co-located` and
  `shared-tag`. Every shared-value relation goes *through* its hub node, so a tag on 30 documents
  is 30 spokes rather than 435 pairwise edges, and hub spokes are damped at read time by the hub's
  own degree (`1/section-size`, `1/dir-size`, `1/tag-degree`) with flow between two members being
  the product of both spokes. `authored` edges stay in `links` and are resolved to `doc` nodes at
  read time, so an authored link keeps exactly one home; only a *local* document has a `doc` node,
  so a cross-KB row never enters the graph in either direction. Weights are frozen (decision 13).

  **`schema_version` goes to 3, so every KB rebuilds once — `pnk sync --rebuild`.** There are no
  migrations, by design.

  **Nothing on a released surface changes.** `pnk links` and `pinakes_links` still return documents
  only; the structural graph is read by the expansion channel and nothing else. Their `--json`
  output on both committed corpora is compared byte-for-byte against a fixture captured before the
  bump.

  Measured, since derivation runs on every sync and `pnk sync` runs on three git hooks:
  `tests/demo-kb` 192 edges and `tests/partner-kb` 171, each derived in under 2 ms; the 300-document
  / 106 806-chunk RFC realism corpus derives 214 608 edges in **1.3 s** and adds 31 MB to a 265 MB
  index; one document of 32 000 chunks with a full heading hierarchy derives in 0.6 s. That corpus's
  per-kind counts — `sibling` 106 506, `shared-tag` 643, `co-located` 262 — reproduce the numbers the
  go decision was taken on exactly.

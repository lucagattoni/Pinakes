# notes

The smallest useful blueprint: plain Markdown under `docs/`, structural chunking, hybrid retrieval.

- Put `.md` or `.txt` files anywhere under `docs/`. Anything under a `drafts/` directory is ignored.
- `pnk sync` gives every document a sidecar carrying its permanent id. Commit those.
- `pnk search "…"` searches locally and for free.

`[retrieval.confidence]` ships commented out on purpose. Thresholds are only meaningful for the
corpus and reranker they were fitted against, so until you fit your own, `pnk search` says
`confidence: unknown` rather than inventing a number. `eval/questions.yaml` is where a golden set
starts.

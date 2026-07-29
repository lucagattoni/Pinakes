- **`pnk sync` no longer destroys a sidecar it cannot parse, and no longer aborts over one.** A
  sidecar that failed to load — a hand-edited `links[]` entry with one wrong character in a ULID is
  the cheapest way there — was dropped from the walk, which made its document look like one that
  had never been ingested, and the mint path then wrote a freshly minted sidecar **over** it. The
  document's permanent ULID and every authored link went with it, `pnk sync` reported success with
  no failures, and `pnk doctor` afterwards reported every sidecar readable and no duplicate ids,
  because the evidence had been overwritten by the thing that destroyed it. Minting now refuses
  where a file already exists, and names the parse error rather than merely the existence. A second
  path had the opposite fault: for an *already-indexed* document whose sidecar breaks while its
  content is unchanged — the likeliest way a user meets this at all — the error escaped `sync()`
  entirely, so one hand-broken file aborted the whole corpus with no failures row and no commit.
  Both now record a failure and let the run continue. One consequence to know about: because
  `--sidecars-only` can now fail, a `pre-commit` hook blocks a commit that stages a document whose
  sidecar will not parse. Present since v0.1.

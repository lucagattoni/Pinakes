- **`pnk sync` no longer destroys a sidecar it cannot parse.** A sidecar that failed to load — a
  hand-edited `links[]` entry with one wrong character in a ULID is the cheapest way there — was
  dropped from the walk, which made its document look like one that had never been ingested, and
  the mint path then wrote a freshly minted sidecar **over** it. The document's permanent ULID and
  every authored link went with it, `pnk sync` reported success with no failures, and `pnk doctor`
  afterwards reported every sidecar readable and no duplicate ids, because the evidence had been
  overwritten by the thing that destroyed it. Minting now goes through `sidecar.create`, which
  refuses to write where a file already exists; the document is left untouched and recorded as a
  failure naming the parse error, and one unparseable sidecar still does not stop the other
  documents from being indexed. Present since v0.1.

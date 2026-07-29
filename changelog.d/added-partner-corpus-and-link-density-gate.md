- **A second synthetic corpus, sparse authored links across both, and a gate that keeps them
  sparse** (L1 of the links release). `tests/partner-kb/` is a partner museum that transacts with
  the archive in `tests/demo-kb/` — loans both ways, courier and condition reporting, a shared
  emergency plan, a joint digitisation programme. 21 documents, its own KB ULID and manifest, and
  no golden set: cross-KB behaviour is verified by traversing it, not by scoring it. Both corpora
  gain forward-authored links (the demo KB had none), and `tools/link_density_gate.py` — in
  `check.sh` and its own CI job — caps the share of documents carrying links, caps any one
  document's degree separately (density alone permits a single hub wired to everything), and
  requires at least one same-KB link per corpus. It reads the committed sidecars and never an
  index, so it runs where no index exists and counts the same population `pnk doctor` reports.
  Nothing about retrieval changes: the golden-set numbers are identical.

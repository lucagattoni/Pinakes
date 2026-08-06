- **The metadata prefix, and a refusal that fires before it can be truncated away.**
  `chunk.metadata_prefix` builds the `title > heading_path` string the injection experiment
  prepends, with section numbers stripped **by construction** — `Chunk` now carries
  `unnumbered_heading_path` beside `heading_path`, filled from the `(number, label)` pair the
  numbered-heading grammar already parsed, so nothing re-parses a joined string and a heading whose
  text legitimately begins with a digit keeps its digits. `chunk.embedding_text` is what gets
  embedded once injection is on; a chunk with neither a title nor a heading path is embedded
  exactly as it is today.
  `chunk.assert_prefix_fits` refuses a corpus whose longest prefix does not fit the reserve
  `[chunking] max_tokens` left for it, naming that prefix and the `max_tokens` to lower to. It runs
  **after chunking and before embedding**, because a prefix is built from `heading_path` and its
  length is a property of the documents, not of the manifest: measured 20260806, 30 tokens on
  RFC 9110 and 68 across 195 RFCs of the same era. `assert_chunkable` could not catch this — it
  validates `max_tokens` alone, before anything has been chunked, and an embedding input longer
  than the model's window is truncated with no warning and no error.
  **No behaviour changes for any existing KB**: nothing on the indexing path calls the refusal yet.
  The manifest option that turns injection on ships with the injection itself.

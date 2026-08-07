- **`[chunking] metadata` — prepend `title > heading path` to the text that is embedded.**
  Accepted values `"off"` (the default) and `"prefix"`. With it on, `pnk sync` embeds
  `chunk.embedding_text` instead of `chunk.text`, so a chunk taken from the middle of a long
  section carries its document's title and its section's heading into the vector — the thing a
  continuation chunk otherwise has none of. **`chunks.text`, `char_start` and `char_end` are
  untouched**, so what `search` returns, what citations quote and the byte-identity bound
  `text == source[char_start:char_end]` all stand; only the *embedded* string changes. The lexical
  channel is unreached by design — FTS5 indexes `chunks.text`, and injecting there needs a new
  column and a schema bump.
  **The option is in `[chunking]`, not `[retrieval]`, deliberately.** The index records what it
  was built with through `store.chunking_identity`, so turning injection on is reported as drift by
  both `pnk sync` and `pnk doctor` — and it is the flip that most needs reporting, since it changes
  no chunk's text, hash or span and an incremental sync therefore finds every document unchanged
  and re-embeds nothing. The same key under `[retrieval]` would be silent, and the user would
  search uninjected vectors with every command reporting success.
  `chunk.assert_prefix_fits` — which shipped dormant — is now called after chunking and before
  embedding whenever the option is on, so a corpus whose prefix does not fit the reserve
  `max_tokens` leaves is refused per document rather than silently truncated by the embedder. With
  the option off it is not called at all: a KB that is not prefixed is not at risk, and refusing it
  would make an opt-in feature a breaking change.
  Enumerated rather than boolean, and **not stamped into the template**: `pinakes.toml` hard-errors
  on an unknown key, so a manifest carrying this one could not be read by an older Pinakes at all.

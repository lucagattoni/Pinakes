- **`the sentence-transformers backend is not installed` now names the free fix on a `[light]`
  install.** When the configured embedding or rerank provider is missing but a registered
  alternative is already importable (checked with `find_spec`, never by loading it), the error
  names it and the two manifest lines to flip — `provider` in `[embedding]` and `[rerank]` — instead
  of only offering the ~2 GB `sentence-transformers` install the `[light]` extra exists to avoid.
  The plain install-line remedy is unchanged when no alternative is installed.

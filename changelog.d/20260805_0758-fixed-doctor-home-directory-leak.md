- **`pnk doctor` no longer prints the operator's home directory.** Three checks (`sidecars`,
  `index`, `unknown outcomes`, plus every check under `_backends`) forwarded another module's
  exception text as-is, and `store.py`'s `StoreError`/`IndexSchemaError`, `sidecar.py`'s
  `SidecarError` and `budget/ledger.py`'s `LedgerError` all build that text from an absolute path
  — always inside `.pinakes/` or under a sidecar's own directory, since `manifest.root` is
  resolved absolute. A new `_de_homed` helper strips the KB root's prefix from any message or
  remedy doctor.py forwards, so a FAIL line pasted into an issue no longer carries a home
  directory with it. A path genuinely outside the KB — the model cache, a linked KB, a packaged
  `prices.toml` — is left exactly as printed; only what sits under the KB root is rewritten
  (`plans/20260731_1202-open-corrections.md` item 5).

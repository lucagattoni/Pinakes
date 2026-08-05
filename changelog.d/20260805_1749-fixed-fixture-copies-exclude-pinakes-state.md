- **Tests that copy a fixture KB no longer copy whatever `.pinakes/` the developer left in it.**
  Five `shutil.copytree` call sites took the whole `tests/demo-kb` or `tests/partner-kb` directory,
  generated index included, so a leftover local index from an earlier manual `pnk sync` was carried
  into the test workspace and used. On a checkout holding one written before the graph release's
  `schema_version` 3 bump, three tests failed with `IndexSchemaError` — on a machine where nothing
  was wrong with the code. All five now pass `ignore=shutil.ignore_patterns(".pinakes")`, the guard
  four other call sites already used.

- **The paid extractor's API key is `PINAKES_ANTHROPIC_API_KEY`, and pinakes now passes it to the
  SDK explicitly.** `anthropic.Anthropic()` was constructed without `api_key`, so the SDK read
  `ANTHROPIC_API_KEY` out of whatever environment it happened to be in. On any machine where that
  variable is exported for some other tool — an editor, an agent, an inherited shell — the paid
  path had a live key nobody aimed at it, and the *"deliberate act of supplying the key"* the
  design counts as a defence was not one. `resolve_api_key` reads the pinakes-specific name,
  refuses a missing or blank value by name with a remedy, and **has no fallback to
  `ANTHROPIC_API_KEY`** — a fallback would restore the whole defect silently. **Breaking for anyone
  running the paid extractor:** rename the variable in your `.env`. The free path is untouched, and
  the caps and the enumerated allowlist bound spend exactly as before.

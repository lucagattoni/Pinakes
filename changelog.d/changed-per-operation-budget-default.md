- **`[budget] per_operation_eur` default raised `0.05` → `0.30`.** The cap bounds one whole
  invocation, not one API call. Measured against the bundled prices (`claude-opus-5`, $5/$25 per
  Mtok, `usd_per_eur` 1.08), one synthesis round costs €0.083 at 8k-in/2k-out and €0.148 at
  12k-in/4k-out — so the old default admitted **zero** rounds of any multi-call paid operation and
  refused it before it began. `0.30` admits two such rounds. `confirm_above_eur` stays at `0.01`,
  so a paid operation still prompts before it spends: this raises the ceiling, never the silence
  below it. **Existing KBs are unaffected** — `pnk init` writes the value into the manifest, so only
  a KB omitting the key, or a newly `pnk init`ed one, sees the new default. `daily_eur` (`1.00`) and
  `monthly_eur` (`5.00`) are unchanged and now bind sooner in relative terms: three full-cap
  operations a day, sixteen a month.

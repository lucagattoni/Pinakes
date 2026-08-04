- **`[budget] per_operation_eur` default raised `0.05` → `0.30`.** The cap bounds one whole
  invocation, not one API call. Measured against the bundled prices (`claude-opus-5`, $5/$25 per
  Mtok, `usd_per_eur` 1.08), one synthesis round costs €0.083 at 8k-in/2k-out and €0.148 at
  12k-in/4k-out — so the old default admitted **zero** rounds of any multi-call paid operation and
  refused it before it began. `0.30` admits two such rounds. `confirm_above_eur` stays at `0.01`,
  so a paid operation still prompts before it spends: this raises the ceiling, never the silence
  below it. **Existing KBs are unaffected** — `pnk init` writes the value into the manifest, so only
  a KB omitting the key, or a newly `pnk init`ed one, sees the new default.
- **`[budget] monthly_eur` default raised `5.00` → `30.00`**, in proportion, so the pair still
  allows roughly a hundred paid operations a month as it did before. At `5.00` the raised
  per-operation cap would have left only sixteen. `daily_eur` stays `1.00` and is now **the binding
  sequence limit**: three full-cap operations a day, and 1.00/day over a 30-day month is 30.00, so
  the monthly ceiling is reached only in a 31-day month at full daily spend. That is deliberate —
  the burst limiter is the one doing the work, and the monthly cap is the backstop behind it.

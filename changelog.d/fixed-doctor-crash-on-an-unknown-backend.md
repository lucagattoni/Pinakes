- **`pnk doctor` crashed on a KB whose PDFs name an extraction backend this install does not know**
  — a KB written by a newer pinakes, or one whose extra has since been uninstalled.
  `is_paid_backend` raises on an unrecognised name, and a health check may not be the thing that
  fails on an unhealthy KB. It now reports them, exactly as the §4.4 coherence check already did.
- **A KB whose PDFs are all paid-extracted no longer gets a permanent `text yield` warning** whose
  remedy would have spent money. They are skipped deliberately, and the check now says so.
- **`pinakes_get` reports an out-of-range page bound as the bound the caller passed**, not as a
  range it never asked for: `page_start=5` on a two-page document said "pages 5-2 is not a range
  within it".

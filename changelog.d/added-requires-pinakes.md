- **`[kb] requires_pinakes` — a manifest can declare the oldest pinakes that can read it.** Unknown
  keys are a hard error by design, so a KB written by a newer pinakes previously failed on the first
  key this build had never heard of and reported it as a typo, when the real problem was an
  out-of-date pinakes. The floor is read in a pre-pass **before** strict validation — after it, the
  parse has already died on the unknown key and the field would be unreachable in exactly the case
  it exists for. A floor only (`">=0.6"`): a KB is readable by the version that wrote it or any
  newer one, so there is no ceiling to express and no specifier grammar to parse. Absence means no
  floor declared, never a refusal, and `pnk init` does not stamp the field — a fresh KB carries no
  key an older pinakes would choke on, so a stamped floor would lock out readers for no gain.

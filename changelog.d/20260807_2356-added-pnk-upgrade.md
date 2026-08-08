- **`pnk upgrade` — what your template changed since the KB was stamped, and whether each change
  still fits your manifest.** It writes nothing: not `pinakes.toml`, not anything under `.pinakes/`.
  The diff it prints is the **recorded** template version against the **installed** one, both
  rendered from the archive through one context, so nothing you wrote appears in it as a change — a
  value you tuned that the template renders cancels on both sides, and a literal you edited never
  enters either side, because neither side is your file. It does appear as unchanged *context* where
  a hunk covers it, and that is the distinction: the context lines are yours, the `+`/`-` lines are
  the template's.
- **Each change is then placed against your manifest, and there are three answers, not two.**
  *applies cleanly* — the lines it expects are there, contiguous, in order, at exactly one place.
  *already applied* — the change is already in your file, because you adopted it by hand or a newer
  `pnk init` wrote it; reporting that as "clean" is what would make a later `--apply` duplicate a
  key. *conflicts* — the lines it expects are not in your file the way it expects them (you edited
  that region, they are in a different order, or they match in two places), so nothing can be
  placed mechanically and the diff is what to apply by hand.
- **A conflict is not a failure and exits `0`.** The command writes nothing, so it has nothing to
  fail at, and exiting non-zero there would make `pnk upgrade` unusable beside `pnk doctor` in one
  script. One code is new and it is this command's alone: **`3` means no baseline** — the comparison could
  not be made and no action of yours would make it possible. **Every KB in existence gets `3`
  today**, because `notes@1.0` was never archived; the message says so, names the comparison
  available now, and promises nothing a later release cannot keep. `1` still means what it means
  everywhere else: something is wrong and it is yours to fix.
- **Scope is `pinakes.toml` alone, stated as a boundary rather than left as a gap.** A template also
  ships a `README.md` and a starter `eval/questions.yaml`; `pnk upgrade` touches neither, because
  your `eval/questions.yaml` is your golden set and the template's is a stub with a header.
- `--json` carries the same diff, the same hunks in the same order, and the same counts — and stays
  JSON on the path that makes no comparison, so a scripted caller never gets prose where it was
  promised a document.

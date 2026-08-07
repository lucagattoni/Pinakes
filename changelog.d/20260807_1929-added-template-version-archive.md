- **`pnk doctor` now warns that your KB's template is out of date — on every KB created before
  this release, which is every KB in existence.** That is the point of the change, not a
  side-effect of it. The check has existed since 0.1 and has never once been able to fire: the
  `notes` template declared `version = "1.0"` in every commit since it was written, while the files
  that version denotes changed in ten later ones. Every KB recorded `notes@1.0`, the installed
  template was also `notes@1.0`, and `pnk doctor` reported `OK` — for eleven different template
  contents. `notes` is now `1.1`, so the comparison finally means something. Nothing is applied
  automatically and no KB needs changing; `pnk upgrade` is what will diff and apply, and it is not
  built yet.
- **A template's content is archived under `src/pinakes/templates/<name>/_versions/<version>/` and
  travels in the wheel**, with `templates/_versions.toml` recording the SHA-256 of each. A KB
  records a reference, never the content, so without the archive nothing on your machine can say
  what `notes@1.1` *meant* — which is why `pnk upgrade` could never have worked. `1.0` is
  deliberately **not** archived: it denotes eleven different contents, so any single answer would
  be wrong for ten of them, and a diff computed from the wrong base is worse than no diff.
- **`tools/template_drift_gate.py`, in `check.sh` and its own CI job** — seven legs, so that
  editing a template without bumping its version is now a red build rather than a convention
  nobody followed. It reports which mode it ran in every time: its history leg needs a full clone
  and *says* when it has been skipped, because a skip is not a pass.
- **`pnk init --template` refuses a name that is not a single path component.** `notes/../notes`
  and `../templates/notes` both resolved to a real template before, and `notes/eval` raised a bare
  `FileNotFoundError` rather than a message. Harmless while every directory under the package root
  was a template — but with the archive present, `--template notes/_versions/1.1` would have
  stamped a KB from a version nobody released.

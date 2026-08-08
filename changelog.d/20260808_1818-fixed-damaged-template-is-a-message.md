- **A damaged template install is a message, never a traceback.** Every read of a template's own
  files was unguarded, so an incomplete or third-party install raised something that is not a
  `PinakesError` and the CLI printed a stack trace: a `_versions/<v>/` without its
  `pinakes.toml.j2` gave `FileNotFoundError`, an unreadable file `PermissionError`, a non-UTF-8 one
  `UnicodeDecodeError`, a malformed `template.toml` a `tomllib.TOMLDecodeError`, and an unclosed
  `{{` a `jinja2.TemplateSyntaxError` — which `_render` never saw, because it is raised by
  `Template(...)` rather than by `render`. All five now name the template, the version and the file.
  The correction covers `describe`, `declared_files`, `render_manifest`, `render_archived` and
  `copy_extras`: the record named the first two, and shipping those alone would have left the same
  defect three functions away.

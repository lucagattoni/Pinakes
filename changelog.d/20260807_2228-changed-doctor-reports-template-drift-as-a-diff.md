- **`pnk doctor` now says *how far* your template has drifted, not just that it has.** When a KB
  records one version and another is installed, it renders **both archived versions** through one
  context and reports how many lines separate them. The comparison is template-against-template, so
  nothing you wrote is in either side: your `provider = "fastembed"` renders identically on both and
  cancels, and your `final_k = 4` never enters either side, because neither side is your file. A
  report that mixed the two could not tell a template change from your own tuning, and would present
  the second as the first.
- **On every KB in existence it says `cannot compare`, and that is the honest answer.** `notes@1.0`
  denotes eleven different template contents, so it is deliberately not archived — a diff computed
  from the wrong base is worse than no diff. The message says so, names the comparison available
  today (`pnk init` a throwaway directory and diff its `pinakes.toml` against yours), and does not
  promise that a later release fixes it: an unarchived version's content is gone, not pending. KBs
  stamped from `notes@1.1` onward are compared automatically.
- **A version bump that leaves the manifest alone reports `same manifest`, never `0 lines differ`.**
  A template version covers four files and this comparison reads one of them; of the ten commits
  between the `notes` template's first version and its second, five touched only the starter golden
  set. `0 lines differ` would have been true of the manifest and read as *nothing changed*.
- **A template needing a variable this build cannot supply is a message, not a traceback.**
  `jinja2.UndefinedError` is not a `PinakesError`, so it reached the terminal as a stack trace; it
  now names the template, the version and the variable. In `pnk doctor` it is one `WARN` row rather
  than the end of the report — a KB with an unrenderable third-party template is not a broken KB,
  and discarding every other check over it helps nobody.

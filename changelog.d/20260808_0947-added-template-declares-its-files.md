- **A template declares the files it writes into a KB.** `template.toml` gains
  `files = [...]`, replacing the hardcoded `README.md` / `eval/questions.yaml` pair. **An absent key
  still means exactly those two**, so `notes` and every third-party template written against an
  earlier build are unchanged. Each entry is refused if it names the `_versions/` archive, if it
  would write outside the KB, or if it would read outside the template — and every entry is checked
  before any entry is written, so a bad declaration leaves no half-stamped KB behind.

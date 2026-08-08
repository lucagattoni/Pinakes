- **A template cannot change the files it stamps without bumping its version.** The template drift
  gate folds `template.toml`'s new `files` list into its content hash. That file is otherwise
  excluded — deliberately, so that "a version bumped with no content change" can still be detected —
  which would have left the one key deciding *what a KB is stamped with* outside the check the
  archive exists to provide. Only the list is hashed; `name`, `version` and `description` stay out.
  An absent key contributes nothing, so every hash published before this release is unchanged.

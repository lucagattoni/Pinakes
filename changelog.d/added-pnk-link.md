- **`pnk link <source> <target> --rel REL` authors a link** from the command line, writing one
  `links[]` entry into the source document's own sidecar and nothing else. The target takes three
  forms, tried in order: a `pnk://` URI (`pnk://self/…` included), `<alias>:<path>` naming a
  declared `[[links.kb]]`, or a path in this KB. Aliases and `self` are resolved to ULIDs **before**
  anything reaches disk, which is what makes a link mean the same thing on someone else's machine.
  The rewrite goes through the round-trip writer, so comments, quoting, blank lines, key order and
  unknown keys — including one inside a `links[]` entry — all survive.
- **It never mints a sidecar.** A source that has none is refused with `pnk sync` as the remedy: a
  `links[].to` needs a ULID only sync mints, and writing a fresh one over a file that may already
  hold a permanent one is the unrecoverable case. An unreadable source sidecar is reported and left
  exactly as it is; the write itself is rename-atomic.
- **An alias resolves through the partner's own `[kb] id`**, and a disagreement with the local
  `[[links.kb]] id` is refused rather than guessed — one of the two names the wrong KB, and what
  would be written is permanent. A well-formed `pnk://` URI whose target is *not* on this machine is
  written, because both ULIDs are already in it.
- **Running the same `pnk link` twice writes nothing the second time** and says so. Two different
  relations to one target remain two entries.

- **`.env.example` named the one environment variable this project forbids.** It recorded
  `ANTHROPIC_API_KEY=`, and has since before `0.8.0` renamed the paid extractor's key to
  `PINAKES_ANTHROPIC_API_KEY` — the rename swept the code, the docs and the CHANGELOG, and missed
  the file whose entire job is to tell an operator the shape to copy. Anyone who copied it to
  `.env` and filled it in got a `.env` that the extractor refuses **and** that exports, into every
  `uv run --env-file .env` process, the exact variable the Anthropic SDK picks up on its own. That
  is the hazard the rename existed to close, reintroduced by its own example file. It now reads
  `PINAKES_ANTHROPIC_API_KEY=` and says why in a comment. Found by a documentation audit, not by
  use — nothing reads `.env.example`, so nothing could have failed on it.

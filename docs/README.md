# pinakes documentation

| Doc | Answers |
|---|---|
| [**GUIDE.md**](GUIDE.md) | *How do I use this?* Install, first KB, PDFs, search, hooks, MCP, troubleshooting |
| [**CLI.md**](CLI.md) | *What does this flag do?* Every command, every flag, exit codes |
| [**MANIFEST.md**](MANIFEST.md) | *What goes in `pinakes.toml`?* Every manifest and sidecar field, with defaults |
| [**STATUS.md**](STATUS.md) | *Does this exist yet?* Shipped vs planned, the increment ledger, measured numbers |
| [**DESIGN.md**](DESIGN.md) | *Why is it built this way?* Architecture, storage, sync semantics, concurrency, trade-offs |
| [**RETROSPECTIVES.md**](RETROSPECTIVES.md) | *What did we learn?* Per-increment findings, and the design's own review passes |
| [**graph/**](graph/) | Graph-retrieval research shaping v0.3 — fourteen investigations plus the synthesis |

Build plans live in [`plans/`](../plans/); the release history is [`CHANGELOG.md`](../CHANGELOG.md).

---

## Where does a fact live?

**One fact, one home.** Each row is the *only* place that fact belongs; everywhere else links to it.
When an increment lands, this table says which file to edit — usually exactly one.

| Fact | Home | Everywhere else |
|---|---|---|
| Whether a feature is built yet | **STATUS.md** | links to it — never restates a version |
| What a command or flag does | **CLI.md** | `--help` is authoritative; CLI.md adds when and why |
| A manifest or sidecar field, its default, its validation | **MANIFEST.md** | DESIGN gives the rationale and links here |
| How to accomplish a task | **GUIDE.md** | README links to it |
| Why a design decision was taken, and what it costs | **DESIGN.md** | — |
| A measured number (recall, latency, false-confidence) | **STATUS.md** | cited with its date wherever quoted |
| What changed in a release | **CHANGELOG.md** | — |
| What an increment taught us | **RETROSPECTIVES.md** | — |
| What is going to be built, and in what order | **`plans/`** | STATUS.md carries the shipped/planned state only |

The README is deliberately **version-free**: it describes what pinakes *is*, never what release you
are on. That is why it does not go stale.

## Landing a new increment

The docs are built so an increment touches few files. In rough order:

1. **STATUS.md** — flip the increment's row. Merged to `main` but not in a release is **"on `main`,
   unreleased"**, not "shipped": installing from a tag and installing from `main` are different
   answers to "can I use this yet". Move its capability out of "not built" only when a user can
   actually reach it. If it changed a measured number, update it *with the date you measured it*.
2. **CLI.md** — move the surface out of "Planned", or add its flags to the command's table.
3. **MANIFEST.md** — add any new manifest or sidecar key, with its default.
4. **GUIDE.md** — fill the stub if the increment made a task possible that wasn't before.
5. **DESIGN.md** — only if the *rationale* changed. A new flag alone is not a design change.
6. **CHANGELOG.md** — the `[Unreleased]` entry, in the same commit as the code.

`plans/v0.2.md` carries a DESIGN.md amendment table assigning each spec edit to the increment that
makes it true. **Amendments land with their increment, never in advance** — a spec describing
unbuilt behaviour is the failure mode the project's README rule exists to prevent. DESIGN sections
still awaiting an amendment carry a dated note saying so.

**Before assigning a release number, check what has already landed on `main`** ([CLAUDE.md](../CLAUDE.md)).
Another session or worktree may have cut a release since your branch started, so the number you were
about to use — or the one a plan assumes — may already be taken. `plans/v0.2.md` assumed it would cut
`0.2.0` at I9; `0.2.0` shipped after I5 and `0.2.1` after that.

## Conventions

- **Every date carries a time**: `YYYYMMDD HH:MM`, local 24h. Several entries land per day, and a
  bare date loses their order and hides how fresh a "verified" claim is.
- **Read the clock; never compose a timestamp.** Run `date "+%Y%m%d %H:%M"` and paste the result.
- **Docs describe what ships.** Anything unbuilt is labelled with the increment or release that will
  bring it. Check by *running the commands a doc shows*, install line included — an audit at 0.1.2
  found four README claims contradicting the code while the CLI and CHANGELOG were correct.
- `make check` formats Python **inside Markdown fences**, so a docs-only commit can fail the gate.

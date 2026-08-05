## The sync-CPU number, and the instrument proving itself in the field (20260805 21:56)

**The measurement item 3 demanded since 20260804 was finally run, and it reverses the item's own
framing.** 55 modern-era RFCs — 16 557 chunks — rebuilt under `fastembed`:

| | |
|---|---|
| wall-clock | 1 497.7 s (~25 min), 1 451 samples |
| **peak** | **500% — 5.0 of 10 cores** |
| **mean** | **480% — 4.8 of 10 cores** |

**The loop is serial and the backend under it is not.** `sync.py` embeds one document at a time, so
the *loop* is single-threaded — but ONNX Runtime is already using half the machine beneath it. Item
3's own fork therefore resolves against the change it was written to consider:

> *The backend already saturates the machine → the loop is fine, and the win is a bigger batch
> (embedding several documents' chunks in one `embed()` call), not processes.*

It also lands exactly on the trap that item named: *"do not stack a process pool on top of a
threaded backend"*. At 4.8 cores already consumed, **two** workers would take ~9.6 of 10 and
anything beyond oversubscribes. The intuitive fix — a pool sized `os.cpu_count() - 1` — would have
been nine workers on a machine with room for two.

**The instrument proved itself in the field, and it is the reason to trust the number.** Sampled
live from the same process tree:

| process | %cpu |
|---|---|
| `measure_sync_cpu.py` | 0.7 |
| **`uv run`** | **0.0** |
| the actual `pnk sync` python | **491.9** |

The pre-fix tool watched the launched pid — `uv run` — and would have reported **0.0 cores for a
workload using five**. That is not a number anyone would have questioned: it *is* the finding item 3
went looking for, and it would have licensed exactly the process pool this measurement rules out.
A tool whose failure mode is "confirms your hypothesis" is the most expensive kind.

**Bounded, and the bound is stated rather than buried:** `fastembed` only. `sentence-transformers`
needs the 2 GB `[st]` extra and is unmeasured, so nothing here licenses a claim about torch.

**A second number fell out of the same run, unasked:** **15 559 of 16 557 chunks carried a
`heading_path` — 94%**. The corpus that opened this whole line of work indexed 106 806 chunks with
**zero**. The grammar works on real documents, and that is the first evidence of it outside a test.

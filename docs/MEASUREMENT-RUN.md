# The measurement run

**The one thing the paid extractor cannot prove about itself** is how well it reads a page. No
free-path test can: the whole point of the paid path is the pages the free path cannot read at all.
This run is what replaces intuition about extraction *quality* with numbers.

> **Fixture provenance is a different job, and it is done separately.** Four branches now carry
> bodies captured from the live API by
> [`tools/record_claude_fixtures.py`](https://github.com/lucagattoni/pinakes/blob/main/tools/record_claude_fixtures.py), and every fixture
> declares its own provenance
> ([`tests/fixtures/claude/README.md`](https://github.com/lucagattoni/pinakes/blob/main/tests/fixtures/claude/README.md)). To re-record a branch,
> use that tool rather than this runbook — the two spend on different things and answer different
> questions.

It **spends real money and needs a real key**, so it can never be a repo gate — which is exactly
why it is written down here with its steps and its euros rather than described as "measured
somewhere". It was last run 20260729 03:17 for €0.43; [STATUS.md](STATUS.md) carries what it
settled.

## What it costs

About **€4.23 worst case** (priced 20260729 against the shipped `prices.toml`), and typically well
under half that — worst case assumes every request hits `max_tokens`, and five pages of prose
produce roughly half of it.

| Step | Documents | Pages | Worst case |
|---|---|---|---|
| (a) `--estimate-only` over one page | 1 | 1 | €0 — counts tokens, generates nothing |
| (b) one real 5-page extraction | 1 | 5 | €0.33 |
| (c) the scanned stratum | 3 | 10 | €1.30 |
| (d) the free-vs-paid delta | 4 twins + 1 control | 28 | €2.60 |

Re-price it before running — `prices.toml` moves:

```bash
uv run --frozen python -c "
from datetime import datetime
from pinakes.budget.estimate import estimate_document
from pinakes.budget.prices import load_prices
prices = load_prices()
est = estimate_document(pages=5, model='claude-opus-5', prices=prices,
                        now=datetime.now().strftime('%Y%m%d %H:%M'), max_price_age_days=3650)
print(f'one 5-page slice: EUR {est.total_eur:.4f} worst case')
"
```

## Setting up

**A measurement KB with the caps raised explicitly.** The shipped defaults refuse a single slice —
that is correct behaviour, and raising them deliberately is the first step of the measurement, not
an obstacle to work around.

**The key.** Put it in `.env` at the repo root as **`PINAKES_ANTHROPIC_API_KEY`**, never
`ANTHROPIC_API_KEY` — `.env` and `.env.*` are gitignored, and `.env.example` records the shape.
(It recorded the *wrong* name from 0.8.0's rename until 20260807; if your `.env` predates that,
rename the variable or the extractor refuses.) This repo is public, so a key that is merely
*untracked* is one
`git add -A` from being published; ignoring it by pattern is what makes that impossible rather than
merely unlikely.

**Nothing loads `.env` automatically, and that is deliberate.** Pinakes has no `.env` support and
should not get any: a tool that can spend money must not pick up credentials from a file nobody
pointed it at, or the same `pnk sync` means different things depending on which directory you ran
it from. Pass it explicitly at the call site, exactly as every other spend control in this project
is explicit:

```bash
uv sync --frozen --extra light --extra pdf --extra claude

# every paid command below is run through --env-file; nothing else needs it
uv run --env-file .env pnk --version      # sanity check: the key is only read when a call is made
```

Verify it actually arrives before spending anything on the assumption that it did:

```bash
uv run --frozen --env-file .env python -c "
import os; key = os.environ.get('PINAKES_ANTHROPIC_API_KEY', '')
print('key reaches the process:', bool(key), '| length:', len(key))
"
```

Then create the measurement KB:

```bash
pnk init /tmp/measure-kb
cd /tmp/measure-kb
```

Then edit `/tmp/measure-kb/pinakes.toml`:

```toml
[sources]
include = ["**/*.pdf"]                # init deliberately does not stamp this

[extraction]
backend = "claude-vision"
model   = "claude-opus-5"

[budget]
confirm_above_eur = 5.00              # raised so the run is not a wall of prompts
per_operation_eur = 5.00
daily_eur         = 5.00
monthly_eur       = 5.00
```

> `PINAKES_ALLOW_SPEND` is **not** part of this recipe. It is a pytest condition and never a product
> guard; putting it in a CLI recipe is what would turn it into one. The product's own opt-in is
> already explicit — `[extraction] backend`, `--extract=`, and the accountant.

## The run

Copy the corpus documents in as you go, one step at a time, and check `pnk budget` between steps.

**(a) Fix the input half of the constant — a token count, not a generation.**

```bash
cp <repo>/tests/pdf-corpus/baseline-1p.pdf docs/
uv run --env-file <repo>/.env pnk sync --estimate-only
```

Record the measured input tokens. Compare against `budget/estimate.py`'s `PAGE_TOKEN_CEILING`
(6,000/page) and `PROMPT_TOKENS` (**700** — measured at 571 on 20260729 and rounded up; the
original estimate of 300 understated it by 1.9×, in the *unsafe* direction) — if the real figure is
far below, the reservation is over-conservative and the constant can be tightened, which is this
step's entire purpose. **Compare against the measurement, not against a re-derivation.**

**(b) Fix the output half — one real 5-page extraction.**

```bash
cp <repo>/tests/pdf-corpus/baseline-12p.pdf docs/     # priced per slice; K = 5
uv run --env-file <repo>/.env pnk sync
uv run --env-file <repo>/.env pnk budget
```

Then check, in order:

- `response.model` against the requested alias, with `startswith` — the recorded value is in the
  cache entry's `per_page_provenance`.
- the **thinking/effort pair** in `extract/claude.py` — confirmed or replaced against what the run
  actually shows. If a `<thinking>` fragment ever reaches a page's text, the leak guard turned it
  into a schema retry, and `pnk budget` will show the extra calls.
- `pnk doctor`'s `completeness` line, which is the audit's first real output.

**(c) The scanned stratum — what the paid path exists for.**

```bash
cp <repo>/tests/pdf-corpus/scanned*.pdf docs/
uv run --env-file <repo>/.env pnk sync
```

Score it with `make pdf-eval`'s metrics against the corpus's hand-authored ground truth, and record
the numbers in DESIGN §9 **with date, model, and euros actually spent**, labelled as measured on
synthetic rasters.

**(d) The free-vs-paid delta — decision 10's justification.**

The five text-layer twins **`plans/20260727_1543-v0.2.md` §I2 names** — one per stratum where `layout.py` does
real work, plus the 12-page baseline as a control — each needing `--force` because they are healthy
by design and the paid path correctly refuses to spend on them otherwise. The scanned and
pathological strata supply no twin: a raster is not a text-layer twin, and the pathological
fixture's whole job is to raise.

```bash
cp <repo>/tests/pdf-corpus/{two-column-a,tables-bordered,headers-repeating,ligatures-a,baseline-12p}.pdf docs/
uv run --env-file <repo>/.env pnk sync --force
```

Record the per-metric delta beside the free numbers. This is the one measurement that says whether
bypassing `layout.py` on the paid path costs anything — running-head handling and reading order are
the two stages it skips.

## Afterwards

1. **`prices.toml`** gains the measured per-page constant and its `measured_on`.
2. **DESIGN §9** gains the scanned-quality numbers, with date, model and euros.
3. **DESIGN §7.1** gains the free-vs-paid delta.
4. **`tests/fixtures/claude/`** — **four branches were recorded live on 20260729 03:36** and the
   README already carries per-fixture provenance, so the remaining work is *re-recording* those
   four with `tools/record_claude_fixtures.py` and checking whether any still-authored branch has
   become recordable.
5. **STATUS.md** gains what this run measured. (Its "output quality is not yet measured" claim was
   already dropped when the half-recording landed.)

If the run contradicts the fixtures anywhere, that finding is worth more than the release schedule:
it is the only evidence that can reach the assumption every branch test rests on.

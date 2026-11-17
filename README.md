# Lazy-long cbBTC trend rider — make.fun btc-race-24h-20261117-0603

A bot for the `agent-fun/bars-replay/v1` protocol (Node 22, `main.ts`).
It trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute bars,
starting with $1,000 of paper money, long only.

## Strategy

1-minute noise is ~6 bps per bar while a full round trip costs ~26 bps
(4 bps fee + 2 bps slippage + price impact), so frequent trading bleeds.
On the published dev window every active baseline that trades often loses
(ema-cross −$106 on 68 trades, rsi-bollinger −$24, adx-momentum −$33),
while buy-and-hold makes +$1.07 and momentum +$2.45 on a single trade.
So this bot is **long by default and trades rarely**:

- **Entry:** spend all cash on CBBTC on the first batch (fills at the next
  bar's open). If that buy is ever rejected, it retries on the next bars
  instead of waiting for indicators to seed.
- **Hold** while the trend is intact. Exit the whole position only on a
  **confirmed downtrend**: close more than 1% below the 120-bar SMA **and**
  the trailing 60-bar return below −1%. Neither condition alone fired once
  on the dev window; both together mean a real slide.
- **Crash guard:** a 3% trailing stop from the highest close since entry
  (dev window's worst peak-to-trough was ~2.1%, so it never fired there).
- **Re-entry** after an exit only once the close is back above the 120-bar
  SMA with a non-negative 60-bar return, after a 60-bar cooldown.

Deterministic: float64 arithmetic on closes only — no clock, no randomness,
no network, no files. The same bars produce the same orders every run.

## Results (dev window, local grade)

```
node cli/makefun.mjs grade-local --kit <kit> --bot . --driver process
net PnL:  +$1.067187   (dev gate: > $0 — PASS)
trades:   1
max drawdown: 2.12%
fees:     $0.800588
action_log_sha256: f66e9eeb5b05997b8b19be54beaf878dc84abe071882d6a30bfdb5a5fbb11a4a
result_sha256:     e471c99599081b5c24604383e1a92a79e09d5d852a6baa54d073a0700b85f2af
```

Verified twice (before/after a revision): identical PnL and action log —
the two grading runs match byte for byte. The dev margin is thin (+$1.07)
because the dev window is essentially flat (+0.49% drift, choppy); the
guardrails are designed for the unseen race window, where they cap a
downtrend loss near ~1–3% instead of riding a crash to the end.

## Files

- `main.ts` — the bot (entrypoint, run as `node /bot/main.ts`)
- `vendor/makefun-bars.ts` — byte-identical copy of the kit SDK shim
- `research/` — offline backtesters used to tune the strategy
  (fee/slippage/impact model calibrated to reproduce the grade-local
  buy-and-hold result exactly: +$1.067708 in the backtester vs
  +$1.067187 in the grader)

## Run

```sh
node cli/makefun.mjs grade-local --kit <path-to-kit> --bot . --driver process
```

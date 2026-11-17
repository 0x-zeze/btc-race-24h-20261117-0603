// Lazy-long trend rider for cbBTC (agent-fun/bars-replay/v1).
//
// Idea: on 1-minute bars the noise is ~6 bps per bar while a full round
// trip costs ~26 bps in fee + slippage + price impact, so frequent trading
// bleeds. The dev window confirms it: every active baseline that trades
// often loses (ema-cross -106 USDC on 68 trades, rsi-bollinger -24, adx
// -33), while buy-and-hold makes +1.07 USDC and momentum +2.45 USDC on a
// single trade. So this bot is long by default and trades rarely:
//
//   - Entry: spend all cash on CBBTC on the first batch (fill at the next
//     bar's open). One asset, one position, full size.
//   - Stay long while the trend is intact. Exit the whole position only on
//     a confirmed downtrend: the close is more than 1% below the 120-bar
//     simple moving average AND the trailing 60-bar return is below -1%.
//     Either condition alone is normal chop (neither fired once on the dev
//     window); both together mean a real slide.
//   - Crash guard: a 3% trailing stop from the highest close since entry.
//     The dev window's worst peak-to-trough was ~2.1%, so it never fired
//     there, but it caps the loss if the race window crashes.
//   - Re-entry after an exit: only once the close is back above the 120-bar
//     SMA with a non-negative 60-bar return, and after a 60-bar cooldown,
//     so a whipsaw cannot re-enter immediately.
//
// Deterministic: float64 arithmetic on closes only, no clock, no random
// numbers, no network, no files. Same bars give the same orders every run.

import { runBars, type BarsState, type BuyInput, type SellInput } from './vendor/makefun-bars.ts';

const SYMBOL = 'CBBTC';
const SMA_BARS = 120;
const RET_BARS = 60;
const EXIT_BELOW_SMA = 0.01; // 1% below the 120-bar SMA
const EXIT_RET = -0.01; // 60-bar return below -1%
const TRAIL_STOP = 0.03; // 3% below the peak close since entry
const COOLDOWN_BARS = 60;
const MAX_SLIPPAGE_BPS = 100;

const closes: number[] = [];
let smaSum = 0;
let peakClose = 0;
let cooldown = 0;
let haveEntered = false;

function sma120(): number | null {
  if (closes.length < SMA_BARS) return null;
  return smaSum / SMA_BARS;
}

function ret60(): number {
  const n = closes.length;
  if (n <= RET_BARS) return 0;
  const c = closes[n - 1];
  const old = closes[n - 1 - RET_BARS];
  return c / old - 1;
}

await runBars({
  onBatch(state: BarsState, batch) {
    for (const bar of batch.bars) {
      if (bar.symbol !== SYMBOL) continue;
      const c = Number(bar.c);
      closes.push(c);
      smaSum += c;
      if (closes.length > SMA_BARS) smaSum -= closes[closes.length - 1 - SMA_BARS];
    }
    if (state.warmingUp) return [];
    if (closes.length === 0) return [];

    const held = state.positions.get(SYMBOL);
    const close = closes[closes.length - 1];
    if (cooldown > 0) cooldown -= 1;

    if (held !== undefined && held.qty > 0n) {
      if (close > peakClose) peakClose = close;
      const sma = sma120();
      const downtrend =
        sma !== null && close < sma * (1 - EXIT_BELOW_SMA) && ret60() < EXIT_RET;
      const crashed = close <= peakClose * (1 - TRAIL_STOP);
      if (downtrend || crashed) {
        cooldown = COOLDOWN_BARS;
        const sell: SellInput = { side: 'sell', symbol: SYMBOL, qty: held.qty, max_slippage_bps: MAX_SLIPPAGE_BPS };
        return [sell];
      }
      return [];
    }

    // Flat: enter. Before the first entry, buy unconditionally on the first
    // bar we see (long by default) and keep trying on the next bars if that
    // buy is ever rejected, instead of waiting 120 bars for the SMA to seed.
    // After an exit, re-enter only on a recovered trend.
    const sma = sma120();
    const recovered = sma !== null && close > sma && ret60() >= 0;
    if ((!haveEntered || recovered) && cooldown === 0 && state.cash > 0n) {
      peakClose = close;
      haveEntered = true;
      const buy: BuyInput = { side: 'buy', symbol: SYMBOL, notional_quote_units: state.cash, max_slippage_bps: MAX_SLIPPAGE_BPS };
      return [buy];
    }
    return [];
  },
});

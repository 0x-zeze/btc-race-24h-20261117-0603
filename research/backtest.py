"""Fast offline backtester mirroring agent-fun/bars-replay/v1 fills.

Fills: decision on bar k close -> fill at bar k+1 open.
Buy: fee 4bps on notional; fill price = open*(1+2bps)*(1+a/D),
  a = notional-after-fee in USDC, D = next bar o_depth in USDC.
Sell: proceeds = qty*open*(1-2bps)/(1+a/D) less 4bps fee, a = qty value at open.
Final flatten at last close with same fee/slip/impact.
Prices: price_scale 5 (price units = USDC*1e5), qty_scale 8.
"""
import gzip, json, math

KIT = "/home/hatch/workspace/makefun/kits/btc-race-24h-20261117-0603/btc-race-24h-20261117-0603-kit"
BARS = [json.loads(l) for l in gzip.open(f"{KIT}/dataset/bars/CBBTC.ndjson.gz", "rt")]
CLOSE = [int(b["c"]) / 1e5 for b in BARS]          # USDC per BTC
OPEN = [int(b["o"]) / 1e5 for b in BARS]
DEPTH = [int(b["o_depth"][0]) / 1e6 for b in BARS]  # USDC
N = len(BARS)
FEE = 0.0004
SLIP = 0.0002


def run(strategy, verbose=False):
    cash = 1000.0
    qty = 0.0
    cost = 0.0  # cost basis (cash spent incl fee) of current position
    peak = 1000.0
    maxdd = 0.0
    trades = 0
    fees = 0.0
    entries = []  # (bar_idx, price)
    # strategy decides at close of bar k; fill happens at open of k+1.
    # pending order: (side, size) executed at next open
    pending = None
    equity_curve = []
    for k in range(N):
        # execute pending order at this bar's open
        if pending is not None:
            side, size = pending
            pending = None
            o, D = OPEN[k], max(DEPTH[k], 1.0)
            if side == "buy" and cash >= size and size >= 1.0:
                a = size * (1 - FEE)
                px = o * (1 + SLIP) * (1 + a / D)
                q = a / px
                qty += q
                cost += size
                cash -= size
                fees += size * FEE
                trades += 1
                entries.append((k, px))
            elif side == "sell" and qty > 0:
                a = qty * o
                px = o * (1 - SLIP) / (1 + a / D)
                proceeds = qty * px
                fee = proceeds * FEE
                cash += proceeds - fee
                fees += fee
                qty = 0.0
                cost = 0.0
                trades += 1
        eq = cash + qty * CLOSE[k]
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / 1000.0)
        equity_curve.append(eq)
        if k < N - 1:
            pending = strategy(k, CLOSE, cash, qty, cost, eq)
    # final flatten at last close
    if qty > 0:
        o, D = CLOSE[-1], max(DEPTH[-1], 1.0)
        a = qty * o
        px = o * (1 - SLIP) / (1 + a / D)
        proceeds = qty * px
        fee = proceeds * FEE
        cash += proceeds - fee
        fees += fee
        trades += 1
        qty = 0.0
    return {"pnl": cash - 1000.0, "trades": trades, "maxdd": maxdd, "fees": fees,
            "final": cash}


def ema_series(closes, span):
    out = [None] * len(closes)
    k = 2 / (span + 1)
    v = None
    for i, c in enumerate(closes):
        if v is None:
            if i + 1 >= span:
                v = sum(closes[i - span + 1:i + 1]) / span
        else:
            v += k * (c - v)
        out[i] = v
    return out


def sma_series(closes, span):
    out = [None] * len(closes)
    s = 0.0
    for i, c in enumerate(closes):
        s += c
        if i >= span:
            s -= closes[i - span]
        if i + 1 >= span:
            out[i] = s / span
    return out


def make_strategy(fast=20, slow=60, sma_len=120, trend_min=0.0015,
                  stop_pct=0.008, trail_pct=0.006, cooldown=30):
    fast_e = ema_series(CLOSE, fast)
    slow_e = ema_series(CLOSE, slow)
    sma = sma_series(CLOSE, sma_len)
    state = {"in": False, "entry_px": 0.0, "peak_px": 0.0, "cool": 0,
             "prev_gap": None}

    def strat(k, closes, cash, qty, cost, eq):
        c = closes[k]
        fe, se, sm = fast_e[k], slow_e[k], sma[k]
        if fe is None or se is None or sm is None:
            return None
        gap = fe - se
        prev = state["prev_gap"]
        state["prev_gap"] = gap
        if state["cool"] > 0:
            state["cool"] -= 1
        if qty > 0:
            state["peak_px"] = max(state["peak_px"], c)
            # exit: cross down, stop-loss, trailing stop
            if (prev is not None and gap < 0 and prev >= 0) or \
               c <= state["entry_px"] * (1 - stop_pct) or \
               c <= state["peak_px"] * (1 - trail_pct):
                state["in"] = False
                state["cool"] = cooldown
                return ("sell", 0)
            return None
        # flat: enter on cross up with trend confirmation
        if state["cool"] == 0 and prev is not None and gap > 0 and prev <= 0:
            ret60 = (c / closes[max(0, k - 60)] - 1) if k >= 60 else 0
            if c > sm and ret60 > trend_min:
                state["in"] = True
                state["entry_px"] = c
                state["peak_px"] = c
                return ("buy", cash)
        return None
    return strat


if __name__ == "__main__":
    import itertools
    best = []
    for fast, slow, sma_len, trend_min, stop_pct, trail_pct, cool in itertools.product(
            [12, 20, 30], [60, 90, 120], [120], [0.0, 0.0015, 0.003],
            [0.008, 0.015], [0.006, 0.012], [30]):
        s = make_strategy(fast, slow, sma_len, trend_min, stop_pct, trail_pct, cool)
        r = run(s)
        best.append((r["pnl"], r["trades"], r["maxdd"], fast, slow, trend_min, stop_pct, trail_pct))
    best.sort(reverse=True)
    print("top 15 by dev PnL (pnl, trades, maxdd, fast, slow, trend_min, stop, trail):")
    for b in best[:15]:
        print(f"  pnl={b[0]:+.2f} trades={b[1]} maxdd={b[2]:.3f} fast={b[3]} slow={b[4]} trend={b[5]} stop={b[6]} trail={b[7]}")
    print("worst 3:")
    for b in best[-3:]:
        print(f"  pnl={b[0]:+.2f} trades={b[1]} maxdd={b[2]:.3f} fast={b[3]} slow={b[4]} trend={b[5]} stop={b[6]} trail={b[7]}")

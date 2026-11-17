"""Sweep strategy family 2: Donchian breakout, slow SMA cross, hold-with-guard."""
import sys
sys.path.insert(0, "/home/hatch/workspace/makefun/entries/btc-race-24h-20261117-0603")
from backtest import run, CLOSE, N, sma_series, ema_series


def donchian(n=60, stop_pct=0.01, trail_pct=0.008, cooldown=20):
    def strat(k, closes, cash, qty, cost, eq):
        if k < n:
            return None
        c = closes[k]
        hi = max(closes[k - n:k])
        lo = min(closes[k - n:k])
        if qty > 0:
            if c <= lo or c <= strat.px * (1 - stop_pct) or c <= strat.pk * (1 - trail_pct):
                strat.cool = cooldown
                return ("sell", 0)
            strat.pk = max(strat.pk, c)
            return None
        if strat.cool > 0:
            strat.cool -= 1
            return None
        if c > hi:
            strat.px = c
            strat.pk = c
            return ("buy", cash)
        return None
    strat.px = 0.0
    strat.pk = 0.0
    strat.cool = 0
    return strat


def hold_guard(sma_len=120, exit_drop=0.01, reenter=True, cooldown=60):
    sma = sma_series(CLOSE, sma_len)
    st = {"in": False, "peak": 0.0, "cool": 0, "entry": 0.0}

    def strat(k, closes, cash, qty, cost, eq):
        c = closes[k]
        if sma[k] is None:
            return None
        if qty > 0:
            st["peak"] = max(st["peak"], c)
            # exit: price fell exit_drop below SMA, or 1.5% below peak
            if c < sma[k] * (1 - exit_drop) or c <= st["peak"] * 0.985:
                st["in"] = False
                st["cool"] = cooldown
                return ("sell", 0)
            return None
        if st["cool"] > 0:
            st["cool"] -= 1
            return None
        # enter: first chance, or re-enter when price back above SMA
        if (k == sma_len) or (reenter and c > sma[k]):
            st["in"] = True
            st["peak"] = c
            st["entry"] = c
            return ("buy", cash)
        return None
    return strat


def slow_cross(fast=60, slow=240, stop_pct=0.01, trail_pct=0.01):
    fe = ema_series(CLOSE, fast)
    se = ema_series(CLOSE, slow)
    st = {"prev": None, "px": 0.0, "pk": 0.0}

    def strat(k, closes, cash, qty, cost, eq):
        if fe[k] is None or se[k] is None:
            return None
        c = closes[k]
        gap = fe[k] - se[k]
        prev = st["prev"]
        st["prev"] = gap
        if qty > 0:
            st["pk"] = max(st["pk"], c)
            if (prev is not None and gap < 0 and prev >= 0) or c <= st["px"] * (1 - stop_pct) or c <= st["pk"] * (1 - trail_pct):
                return ("sell", 0)
            return None
        if prev is not None and gap > 0 and prev <= 0:
            st["px"] = c
            st["pk"] = c
            return ("buy", cash)
        return None
    return strat


def split_half(strategy_fn):
    """PnL on first 720 bars and last 720 bars separately (fresh $1000 each)."""
    import backtest
    orig_close, orig_open, orig_depth, orig_n = backtest.CLOSE, backtest.OPEN, backtest.DEPTH, backtest.N
    res = []
    for a, b in [(0, 720), (720, 1440)]:
        backtest.CLOSE = orig_close[a:b]
        backtest.OPEN = orig_open[a:b]
        backtest.DEPTH = orig_depth[a:b]
        backtest.N = b - a
        # strategy functions close over global CLOSE; rebuild
        r = run(strategy_fn())
        res.append(round(r["pnl"], 2))
    backtest.CLOSE, backtest.OPEN, backtest.DEPTH, backtest.N = orig_close, orig_open, orig_depth, orig_n
    return res


if __name__ == "__main__":
    print("== Donchian ==")
    for n in [30, 60, 120]:
        for stop in [0.008, 0.015]:
            for trail in [0.008, 0.015]:
                r = run(donchian(n, stop, trail))
                print(f"  n={n} stop={stop} trail={trail}: pnl={r['pnl']:+.2f} trades={r['trades']} maxdd={r['maxdd']:.3f}")
    print("== Hold-with-guard ==")
    for sma_len in [60, 120, 240]:
        for ex in [0.005, 0.01, 0.02]:
            r = run(hold_guard(sma_len, ex))
            print(f"  sma={sma_len} exit_drop={ex}: pnl={r['pnl']:+.2f} trades={r['trades']} maxdd={r['maxdd']:.3f}")
    print("== Slow EMA cross ==")
    for fast, slow in [(30, 120), (60, 240), (30, 240), (60, 180)]:
        for stop in [0.01, 0.02]:
            r = run(slow_cross(fast, slow, stop, stop))
            print(f"  fast={fast} slow={slow} stop={stop}: pnl={r['pnl']:+.2f} trades={r['trades']} maxdd={r['maxdd']:.3f}")

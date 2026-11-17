"""Family 3: lazy-long — long by default, exit only on a strong confirmed
downtrend, re-enter on recovery. Calibrate vs grade-local buy-and-hold first."""
import sys
sys.path.insert(0, "/home/hatch/workspace/makefun/entries/btc-race-24h-20261117-0603")
from backtest import run, CLOSE, N, sma_series


def buy_hold(k, closes, cash, qty, cost, eq):
    if k == 0 and qty == 0:
        return ("buy", cash)
    return None


def lazy_long(entry_bar=0, sma_len=240, exit_drop=0.01, exit_ret=-0.01,
              trail=0.03, cooldown=60):
    sma = sma_series(CLOSE, sma_len)
    st = {"peak": 0.0, "cool": 0}

    def strat(k, closes, cash, qty, cost, eq):
        c = closes[k]
        if qty > 0:
            st["peak"] = max(st["peak"], c)
            ret60 = (c / closes[k - 60] - 1) if k >= 60 else 0.0
            sm = sma[k]
            if (sm is not None and c < sm * (1 - exit_drop) and ret60 < exit_ret) or \
               c <= st["peak"] * (1 - trail):
                st["cool"] = cooldown
                return ("sell", 0)
            return None
        if st["cool"] > 0:
            st["cool"] -= 1
            return None
        if k >= entry_bar:
            sm = sma[k]
            ret60 = (c / closes[k - 60] - 1) if k >= 60 else 0.0
            # enter: at entry bar unconditionally (long by default), or on
            # recovery (price back above SMA with non-negative momentum)
            if k == entry_bar or (sm is not None and c > sm and ret60 >= 0):
                st["peak"] = c
                return ("buy", cash)
        return None
    return strat


if __name__ == "__main__":
    print("calibration buy-hold:", run(buy_hold))
    print("== lazy long ==")
    for entry_bar in [0, 30]:
        for sma_len in [120, 240]:
            for ed in [0.005, 0.01, 0.02]:
                for er in [-0.005, -0.01, -0.02]:
                    for trail in [0.03]:
                        r = run(lazy_long(entry_bar, sma_len, ed, er, trail))
                        print(f"  entry={entry_bar} sma={sma_len} exit_drop={ed} exit_ret={er} trail={trail}: "
                              f"pnl={r['pnl']:+.2f} trades={r['trades']} maxdd={r['maxdd']:.3f}")

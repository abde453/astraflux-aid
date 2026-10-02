"""Comparison with experimental data, held-out calibration check, and sensitivity band."""
import math
from .engine import simulate, LEAK_SCALE


def interp(series, t):
    if t <= 0: return 0.0
    pt, pv = 0.0, 0.0
    for s in series:
        if s["t"] >= t:
            return pv if s["t"] == pt else pv + (s["released_pct"] - pv) * (t - pt) / (s["t"] - pt)
        pt, pv = s["t"], s["released_pct"]
    return pv


def _rm(o, p): return math.sqrt(sum((a - b) ** 2 for a, b in zip(o, p)) / len(o))


def metrics(obs, pred):
    n = len(obs); msd = sum((a - b) ** 2 for a, b in zip(obs, pred)) / n
    return {"n": n, "rmse_pct": round(math.sqrt(msd), 3),
            "mae_pct": round(sum(abs(a - b) for a, b in zip(obs, pred)) / n, 3),
            "f2": round(50 * math.log10(100 / math.sqrt(1 + msd)), 2)}


def band(core, coating, polymer, envs, k, dt, sample):
    runs = [simulate(core, coating, polymer, envs, k * a, dt, sample, LEAK_SCALE * b).series
            for a in (0.5, 2.0) for b in (0.5, 2.0)]
    n = len(runs[0])
    return {"t": [s["t"] for s in runs[0]],
            "lo": [min(r[i]["released_pct"] for r in runs) for i in range(n)],
            "hi": [max(r[i]["released_pct"] for r in runs) for i in range(n)],
            "definition": "Envelope of 4 runs with k_base and leak_scale each scaled x0.5 / x2. Sensitivity to uncalibrated constants, NOT a statistical confidence interval."}


def calibrate(run_k, ts, obs, k_nom):
    """Fit k_base on training points (i%3 != 2); report error on held-out points (i%3 == 2)."""
    n = len(ts)
    te = [i for i in range(n) if i % 3 == 2]; tr = [i for i in range(n) if i % 3 != 2]
    if len(te) < 2: raise ValueError("At least 6 data points are needed (2+ held out for testing).")
    ot, oe = [obs[i] for i in tr], [obs[i] for i in te]
    P = lambda s, idx: [interp(s, ts[i]) for i in idx]
    trm = lambda k: _rm(ot, P(run_k(k), tr))
    grid = [10 ** (-5 + 5 * j / 60) for j in range(61)]
    sc = [trm(k) for k in grid]; j = min(range(61), key=sc.__getitem__)
    lo, hi = math.log10(grid[max(j - 1, 0)]), math.log10(grid[min(j + 1, 60)])
    kf = min((10 ** (lo + (hi - lo) * i / 20) for i in range(21)), key=trm)
    sf, sn = run_k(kf), run_k(k_nom)
    return {"k_fit": kf, "k_nominal": k_nom, "train_idx": tr, "test_idx": te,
            "train": metrics(ot, P(sf, tr)), "test_calibrated": metrics(oe, P(sf, te)),
            "test_uncalibrated": metrics(oe, P(sn, te)),
            "identifiable": (max(sc) - min(sc)) > 1.0,
            "fitted_series": [{"t": x["t"], "released_pct": x["released_pct"]} for x in sf[::6]],
            "nominal_pred_all": P(sn, range(n))}

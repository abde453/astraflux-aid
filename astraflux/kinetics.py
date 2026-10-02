"""Empirical release-kinetics models for curve fitting (NOT mechanistic proof). t in minutes, F in % released."""
import math
import numpy as np
from scipy.optimize import curve_fit
from scipy import stats

MODELS = {
    "first_order": {"name": "First-order", "equation": "F = 100 * (1 - exp(-k*t))", "params": ["k"], "units": ["1/min"],
                    "limits": "Assumes complete release (100 % plateau)."},
    "higuchi": {"name": "Higuchi", "equation": "F = kH * sqrt(t)", "params": ["kH"], "units": ["%/min^0.5"],
                "limits": "Derived for planar matrices with perfect sink; fitted on points with F <= 60 %."},
    "korsmeyer_peppas": {"name": "Korsmeyer-Peppas", "equation": "F = k * t^n", "params": ["k", "n"], "units": ["%/min^n", "-"],
                         "limits": "Use only F <= 60 %. The meaning of n depends on geometry; n alone does not prove a mechanism."},
}
_F = {"first_order": lambda t, k: 100 * (1 - np.exp(-k * t)),
      "higuchi": lambda t, k: k * np.sqrt(t),
      "korsmeyer_peppas": lambda t, k, n: k * np.power(t, n)}
_P0 = {"first_order": ([0.01], ([1e-9], [10.0])), "higuchi": ([1.0], ([1e-9], [1e3])),
       "korsmeyer_peppas": ([1.0, 0.5], ([1e-9, 0.05], [1e3, 3.0]))}


def predict(model, params, t): return _F[model](np.asarray(t, float), *params)


def _select(model, pts):
    pts = [(t, f) for t, f in pts if t > 0]
    return [(t, f) for t, f in pts if f <= 60.0] if model != "first_order" else pts


def _metrics(obs, pred, p=0):
    obs, pred = np.asarray(obs), np.asarray(pred); n = len(obs); rss = float(np.sum((obs - pred) ** 2)); sst = float(np.sum((obs - obs.mean()) ** 2))
    out = {"n": n, "rmse_pct": round(math.sqrt(rss / n), 4), "r2": round(1 - rss / sst, 4) if sst > 0 else None}
    if p and n - p - 1 > 0 and rss > 0:
        aic = n * math.log(rss / n) + 2 * p; out["aicc"] = round(aic + 2 * p * (p + 1) / (n - p - 1), 3)
    return out


def fit(model, pts):
    if model not in MODELS: raise ValueError(f"Unknown model '{model}'.")
    d = _select(model, pts); p = len(MODELS[model]["params"])
    if len(d) < p + 2: raise ValueError(f"{MODELS[model]['name']}: need at least {p + 2} usable points (got {len(d)}; points with t=0 or F>60 % are excluded where required).")
    t, f = np.array([x[0] for x in d]), np.array([x[1] for x in d])
    p0, bounds = _P0[model]
    try: popt, pcov = curve_fit(_F[model], t, f, p0=p0, bounds=bounds, maxfev=20000)
    except (RuntimeError, ValueError) as e: raise ValueError(f"{MODELS[model]['name']}: fit did not converge ({e}).")
    se = np.sqrt(np.diag(pcov)); dof = len(d) - p; tq = stats.t.ppf(0.975, dof) if dof > 0 else float("nan")
    params = [{"name": MODELS[model]["params"][i], "unit": MODELS[model]["units"][i], "value": float(popt[i]),
               "se": float(se[i]) if np.isfinite(se[i]) else None,
               "ci95": [float(popt[i] - tq * se[i]), float(popt[i] + tq * se[i])] if np.isfinite(se[i]) and np.isfinite(tq) else None} for i in range(p)]
    res = _metrics(f, _F[model](t, *popt), p)
    warns = []
    if len(d) < 6: warns.append("Few points (<6): parameter estimates are unreliable.")
    if len(d) <= p + 2: warns.append("Almost as many parameters as points: risk of overfitting.")
    return {"model": model, "name": MODELS[model]["name"], "equation": MODELS[model]["equation"], "params": params, "fit": res,
            "n_used": len(d), "n_excluded": len(pts) - len(d), "residuals": [round(float(x), 4) for x in f - _F[model](t, *popt)],
            "t_used": [float(x) for x in t], "warnings": warns, "limits": MODELS[model]["limits"],
            "_popt": [float(x) for x in popt]}


def validate(model, popt, pts):
    d = _select(model, pts)
    if len(d) < 2: raise ValueError("Validation dataset has fewer than 2 usable points for this model.")
    t, f = [x[0] for x in d], [x[1] for x in d]
    m = _metrics(f, predict(model, popt, t)); m["pred"] = [round(float(x), 4) for x in predict(model, popt, t)]; m["t"] = t; return m

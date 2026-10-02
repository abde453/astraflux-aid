"""Batch formulation & scaling calculator. Decimal arithmetic, no floating-point drift.
A DRAFT calculation aid: not a validated GMP/BPR system. Results must be reviewed by qualified personnel."""
import hashlib, json
from decimal import Decimal as D, ROUND_CEILING, getcontext

getcontext().prec = 40
ENGINE_VERSION = "1.0"
ROLES = ("API", "Diluent / Filler", "Disintegrant", "Binder", "Lubricant", "Glidant", "Coating", "Other")
Q = D("0.000001")


class BatchError(ValueError):
    """User-facing input problem."""


def _f(x): return float(x.quantize(Q))


def _d(v, name):
    try: return D(str(v))
    except Exception: raise BatchError(f"'{name}' is not a valid number.")


EXAMPLE = {"product": "Paracetamol 500 mg Tablets", "requested_units": 150000, "unit_label": "tablets", "loss_pct": 2.0, "assay_basis": "dried",
           "lines": [{"name": "Paracetamol", "role": "API", "mg_per_unit": 500, "assay_pct": 98.5, "lod_pct": 0.8, "compensates": False},
                     {"name": "Avicel PH-102", "role": "Diluent / Filler", "mg_per_unit": 80, "assay_pct": 100, "lod_pct": 0, "compensates": True},
                     {"name": "Sodium Starch Glycolate", "role": "Disintegrant", "mg_per_unit": 15, "assay_pct": 100, "lod_pct": 0, "compensates": False},
                     {"name": "Magnesium Stearate", "role": "Lubricant", "mg_per_unit": 5, "assay_pct": 100, "lod_pct": 0, "compensates": False}]}

FORMULAS = ["Planned units = ceil(requested units x (1 + loss % / 100))",
            "Theoretical kg = planned units x mg per unit / 1,000,000",
            "Correction factor = 100/Assay % x 100/(100 - LOD %)   [assay basis 'dried'];  100/Assay %  [basis 'as is']",
            "Actual kg (non-compensating line) = theoretical kg x correction factor",
            "Compensating line (filler) actual kg = total theoretical kg - sum of actual kg of all other lines (keeps the batch total constant)"]


def calculate(req: dict) -> dict:
    lines = req["lines"]
    if req["assay_basis"] not in ("dried", "as_is"): raise BatchError("assay_basis must be 'dried' or 'as_is'.")
    comps = [l for l in lines if l.get("compensates")]
    if len(comps) > 1: raise BatchError("Only one line can be the compensating filler.")
    if comps and comps[0]["role"] == "API": raise BatchError("The API cannot be the compensating line.")
    if len({l["name"].strip().lower() for l in lines}) != len(lines): raise BatchError("Ingredient names must be unique.")
    if not any(l["role"] == "API" for l in lines): raise BatchError("The recipe needs at least one line with role 'API'.")
    units = _d(req["requested_units"], "requested_units"); loss = _d(req["loss_pct"], "loss_pct")
    planned = (units * (1 + loss / 100)).to_integral_value(rounding=ROUND_CEILING)
    out, warns = [], []
    for l in lines:
        mg, a, w = _d(l["mg_per_unit"], "mg_per_unit"), _d(l["assay_pct"], "assay_pct"), _d(l["lod_pct"], "lod_pct")
        if l["role"] not in ROLES: raise BatchError(f"Unknown role '{l['role']}'.")
        if mg <= 0: raise BatchError(f"mg per unit of '{l['name']}' must be > 0.")
        if not (0 < a <= 100): raise BatchError(f"Assay of '{l['name']}' must be in (0, 100] %.")
        if not (0 <= w < 100): raise BatchError(f"LOD of '{l['name']}' must be in [0, 100) %.")
        factor = (100 / a) * ((100 / (100 - w)) if req["assay_basis"] == "dried" else 1)
        th = planned * mg / 1_000_000
        out.append({"name": l["name"], "role": l["role"], "mg_per_unit": mg, "assay_pct": a, "lod_pct": w, "factor": factor, "th": th, "act": th * factor, "comp": bool(l.get("compensates"))})
    tot_th = sum(o["th"] for o in out)
    if comps:
        c = next(o for o in out if o["comp"]); others = sum(o["act"] for o in out if not o["comp"])
        corrected = c["th"]; c["act"] = tot_th - others; c["factor"] = D(1)
        if c["act"] <= 0: raise BatchError(f"The corrections exceed the amount of '{c['name']}': reduce the filler adjustment or revise the recipe.")
        if (c["th"] - c["act"]) > c["th"] * D("0.25"): warns.append(f"'{c['name']}' is reduced by more than 25 % of its theoretical quantity; check the assay/LOD inputs.")
    else:
        warns.append("No compensating filler selected: the actual batch total is larger than the theoretical total.")
    tot_act = sum(o["act"] for o in out)
    if comps and abs(tot_act - tot_th) > D("1e-9"): raise RuntimeError("Mass balance check failed.")
    if any(o["factor"] > D("1.05") for o in out): warns.append("A correction factor exceeds 1.05: verify the certificate-of-analysis values.")
    rows = [{"name": o["name"], "role": o["role"], "mg_per_unit": float(o["mg_per_unit"]), "assay_pct": float(o["assay_pct"]), "lod_pct": float(o["lod_pct"]),
             "correction_factor": float(o["factor"].quantize(D("0.000001"))), "theoretical_kg": _f(o["th"]), "actual_kg": _f(o["act"]),
             "difference_kg": _f(o["act"] - o["th"]), "compensating": o["comp"]} for o in out]
    cid = hashlib.sha256((json.dumps(req, sort_keys=True) + ENGINE_VERSION).encode()).hexdigest()[:12]
    return {"calc_id": cid, "engine_version": ENGINE_VERSION, "inputs": req, "planned_units": int(planned),
            "unit_mass_mg": _f(sum(_d(l["mg_per_unit"], "mg") for l in lines)), "lines": rows,
            "totals": {"theoretical_kg": _f(tot_th), "actual_kg": _f(tot_act), "mass_balance_difference_kg": _f(tot_act - tot_th)},
            "warnings": warns, "formulas": FORMULAS,
            "disclaimer": "Draft calculation aid. Not a validated GMP/BPR system and not an approved batch record; it must be verified and approved by qualified personnel under your quality system."}

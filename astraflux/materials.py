"""Material registry, core formulation (mixer) and storage heuristics."""
from __future__ import annotations
import json, hashlib
from pathlib import Path
from .engine import SimulationError

DATA = Path(__file__).parent / "data"


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


APIS = _load("materials_api.json")
EXCIPIENTS = _load("materials_excipients.json")
POLYMERS = _load("polymers.json")
DEFAULT_ENVS = _load("environments.json")


def get_material(name: str) -> dict:
    if name in APIS: return APIS[name]
    if name in EXCIPIENTS: return EXCIPIENTS[name]
    raise SimulationError(f"Unknown material '{name}'.")


def build_core(components: list[dict]) -> dict:
    """components: [{'name': str, 'mass_mg': float}] -> core properties + audit."""
    if not components: raise SimulationError("Formulation needs at least one component.")
    if not any(c["name"] in APIS for c in components):
        raise SimulationError("Formulation must include at least one active ingredient (API).")
    tot = wsol = vol = 0.0
    audit = []
    for c in components:
        m = float(c["mass_mg"])
        if m <= 0: raise SimulationError(f"Mass of '{c['name']}' must be > 0 mg.")
        p = get_material(c["name"])
        dens = p.get("density", 1.0)
        if dens <= 0: raise SimulationError(f"Invalid density for '{c['name']}'.")
        tot += m; wsol += m * p.get("solubility", 0.0); vol += m / dens
        audit.append({"name": c["name"], "mass_mg": m, "properties": p})
    return {"mass": tot, "density": tot / vol, "solubility": wsol / tot, "components": audit}


def storage_recommendation(core: dict) -> dict:
    """Rule-of-thumb heuristic (NOT a stability study)."""
    tot = sum(c["mass_mg"] for c in core["components"])
    hygro = sum(c["mass_mg"] * c["properties"].get("hygroscopicity", 0.1) for c in core["components"]) / tot
    tmin = min(c["properties"].get("temp_limit", 40.0) for c in core["components"])
    # Conservative: never recommend above 25 C ambient (ICH zone I/II) and cap RH at 60%.
    temp = min(25.0, tmin * 0.9)
    rh = max(10.0, min(60.0, 100 - hygro * 100))
    label = "Refrigerated" if temp < 10 else ("Ultra-dry ambient" if rh < 30 else "Controlled room temperature")
    return {"aggregate_hygroscopicity": round(hygro, 3), "min_thermal_limit_c": tmin,
            "target_temp_c": round(temp, 1), "target_humidity_pct": round(rh, 1), "label": label,
            "note": "Heuristic only; real shelf-life requires ICH stability studies."}


DATA_VERSION = hashlib.sha256(b"".join((DATA / n).read_bytes() for n in
    ("materials_api.json", "materials_excipients.json", "polymers.json", "environments.json"))).hexdigest()[:12]

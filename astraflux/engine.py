"""AstraFlux simulation engine (semi-quantitative dissolution model).

Model summary (all constants are UNCALIBRATED assumptions, see docs/LIMITATIONS):
  * Pill = optional polymer coating (outer) + core (mixture of API + excipients).
  * Coating intact & pH <  polymer threshold : core leaks slowly by diffusion
        through the film (rate ~ permeability * diffusion_modifier / thickness).
  * Coating intact & pH >= polymer threshold : coating erodes first-order
        (rate = degradation_rate * agitation); core is exposed as it erodes.
  * Core (no coating left)                    : Noyes-Whitney surface dissolution
        dM/dt = k * agitation * A * (Cs - C), A from remaining volume (sphere).
  * Fluid is one well-mixed 250 mL bath (no gastric emptying / absorption).
Units: mass mg, density g/cm3 (=mg/mm3), solubility mg/mL, area mm2, time s.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

FLUID_ML = 250.0          # assumed dissolution medium volume
LEAK_SCALE = 3e-6         # assumed film-leak scaling (tuned, NOT calibrated)
MAX_STEPS = 200_000       # safety cap for public demo


class SimulationError(ValueError):
    """Raised for invalid inputs; message is safe to show to users."""


@dataclass
class Polymer:
    name: str
    dissolve_pH_threshold: float = 0.0
    permeability: float = 1.0
    degradation_rate: float = 0.01
    diffusion_modifier: float = 1.0


@dataclass
class Environment:
    name: str
    pH: float
    duration: float  # seconds
    agitation: float = 1.0


@dataclass
class Core:
    mass: float
    density: float
    solubility: float


@dataclass
class Coating:
    mass: float
    density: float = 1.0
    thickness: float = 0.05  # mm


@dataclass
class Result:
    series: list = field(default_factory=list)   # downsampled points
    summary: dict = field(default_factory=dict)


def validate(core: Core, coating: Coating | None, envs, dt: float, k_base: float):
    if core.mass <= 0: raise SimulationError("Core mass must be > 0 mg.")
    if core.density <= 0: raise SimulationError("Core density must be > 0.")
    if core.solubility <= 0: raise SimulationError("Core solubility must be > 0 mg/mL.")
    if coating is not None:
        if coating.mass < 0: raise SimulationError("Coating mass cannot be negative.")
        if coating.mass > 0 and (coating.density <= 0 or coating.thickness <= 0):
            raise SimulationError("Coating density and thickness must be > 0.")
    if not envs: raise SimulationError("At least one environment stage is required.")
    if dt <= 0 or dt > 60: raise SimulationError("Time step dt must be in (0, 60] seconds.")
    if k_base <= 0: raise SimulationError("k_base must be > 0.")
    total = 0.0
    for e in envs:
        if not (0 <= e.pH <= 14): raise SimulationError(f"pH of '{e.name}' must be within 0-14.")
        if e.duration <= 0: raise SimulationError(f"Duration of '{e.name}' must be > 0 s.")
        if e.agitation <= 0: raise SimulationError(f"Agitation of '{e.name}' must be > 0.")
        total += e.duration
    if total / dt > MAX_STEPS:
        raise SimulationError("Simulation too long for the chosen dt (reduce duration or increase dt).")


def _area(core_m, coat_m, core: Core, coat: Coating | None):
    vol = core_m / core.density + (coat_m / coat.density if coat else 0.0)  # mm3
    if vol <= 0: return 0.0
    r = (3 * vol / (4 * math.pi)) ** (1 / 3)
    return 4 * math.pi * r * r


def simulate(core: Core, coating: Coating | None, polymer: Polymer | None,
             envs: list[Environment], k_base: float = 0.05, dt: float = 1.0,
             sample_every: float = 10.0, leak_scale: float = LEAK_SCALE) -> Result:
    validate(core, coating, envs, dt, k_base)
    coat_m = coating.mass if (coating and polymer) else 0.0
    coat_obj = coating if coat_m > 0 else None
    core_m = core.mass
    total0 = core_m  # release % is relative to the core (drug-bearing) mass
    C = 0.0
    t = 0.0
    res = Result()
    next_sample = 0.0
    stage_end = {}
    thickness = coating.thickness if coat_obj else 1.0
    for env in envs:
        steps = max(1, int(round(env.duration / dt)))
        for _ in range(steps):
            released = 0.0
            if core_m > 0:
                A = _area(core_m, coat_m, core, coat_obj)
                if coat_m > 0:
                    if env.pH >= polymer.dissolve_pH_threshold:
                        er = min(coat_m, coat_m * polymer.degradation_rate * env.agitation * dt)
                        coat_m -= er
                        if coat_m < 1e-6: coat_m = 0.0
                    # film-limited leakage of core through intact coating
                    p = polymer.permeability * polymer.diffusion_modifier * leak_scale / thickness
                    dM = p * A * max(core.solubility - C, 0.0) * dt
                else:
                    dM = k_base * env.agitation * A * max(core.solubility - C, 0.0) * dt
                released = max(0.0, min(dM, core_m))
                core_m -= released
                C += released / FLUID_ML
            t += dt
            if t >= next_sample:
                res.series.append({"t": round(t, 1), "env": env.name,
                                   "released_pct": round(100 * (total0 - core_m) / total0, 3),
                                   "coating_mg": round(coat_m, 3),
                                   "conc_mg_ml": round(C, 5)})
                next_sample += sample_every
        stage_end[env.name] = round(100 * (total0 - core_m) / total0, 2)
    rel = lambda p: next((s["t"] for s in res.series if s["released_pct"] >= p), None)
    res.summary = {
        "final_released_pct": round(100 * (total0 - core_m) / total0, 2),
        "released_pct_at_end_of_stage": stage_end,
        "t10_s": rel(10), "t50_s": rel(50), "t85_s": rel(85),
        "coated": coat_obj is not None,
        "total_time_s": t,
        "mass_balance_error_mg": round(abs(C * FLUID_ML - (total0 - core_m)), 9),
    }
    return res


MODEL_VERSION = "0.3.0"
MODEL_INFO = {
    "version": MODEL_VERSION,
    "equations": [
        "Core dissolution (Noyes-Whitney): dM/dt = k_base * agitation * A * (Cs - C)",
        "Coating erosion when pH >= polymer threshold: dMc/dt = -degradation_rate * agitation * Mc",
        "Film leakage while coating intact: dM/dt = leak_scale * permeability * diffusion_modifier / thickness * A * (Cs - C)",
        "A = 4*pi*r^2 with r from the remaining tablet volume (sphere); C = released mass / fluid volume",
    ],
    "units": {"mass": "mg", "density": "g/cm3 (= mg/mm3)", "solubility": "mg/mL", "area": "mm2",
              "time": "s (plots in min)", "thickness": "mm", "pH": "-", "fluid_volume": "mL"},
    "constants": {"fluid_volume_mL": FLUID_ML, "leak_scale": LEAK_SCALE, "status": "UNCALIBRATED assumptions (leak_scale tuned for plausible enteric behaviour; k_base default is illustrative)"},
    "assumptions": [
        "Single well-mixed fluid bath; no gastric emptying, absorption or transit",
        "Spherical tablet; surface area from remaining volume",
        "Coating erodes first-order only at pH >= threshold; below it only slow film leakage",
        "No matrix swelling, disintegration or particle-size effects",
        "Excipient/API properties combined by mass-weighted solubility and harmonic density",
    ],
    "validity_domain": ["pH 0-14, film thickness 0.01-2 mm, tablet mass up to ~5 g", "Not validated against experimental dissolution data", "Gastric-resistance flag (<=10% in acid stage) is a screening heuristic"],
    "not_implemented": ["Fitting beyond k_base", "Statistical uncertainty / confidence intervals", "Global sensitivity indices", "ML / PINN models", "Formulation optimisation"],
}

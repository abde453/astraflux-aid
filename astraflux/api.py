"""FastAPI app: serves the demo UI and the simulation API."""
from __future__ import annotations
import os, json, time, hashlib, logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import materials as M, analysis as A
from .store_api import router as store_router
from .engine import Core, Coating, Environment, Polymer, SimulationError, simulate, MODEL_INFO, MODEL_VERSION

log = logging.getLogger("astraflux")
VERSION = "0.3.0-prototype"
STATIC = Path(__file__).parent / "static"
app = FastAPI(title="AstraFlux AI", version=VERSION, description="Drug-delivery dissolution simulation prototype (demo).")
# Public, credential-free demo API. Restrict with env ALLOWED_ORIGINS="https://a.com,https://b.com".
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")],
                   allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Workspace"])


app.include_router(store_router)


class Component(BaseModel):
    name: str = Field(max_length=80)
    mass_mg: float = Field(gt=0, le=5000)

class Stage(BaseModel):
    name: str = Field(max_length=40)
    pH: float = Field(ge=0, le=14)
    duration_s: float = Field(gt=0, le=86400)
    agitation: float = Field(default=1.0, gt=0, le=10)

class SimRequest(BaseModel):
    components: List[Component] = Field(min_length=1, max_length=12)
    polymer: Optional[str] = None
    coating_mass_mg: float = Field(default=0.0, ge=0, le=500)
    coating_thickness_mm: float = Field(default=0.05, gt=0, le=2)
    stages: List[Stage] = Field(min_length=1, max_length=6)
    k_base: float = Field(default=0.05, gt=0, le=5)
    dt_s: float = Field(default=2.0, gt=0, le=60)
    include_band: bool = True

class ExpData(BaseModel):
    times_min: List[float] = Field(min_length=6, max_length=500)
    release_pct: List[float] = Field(min_length=6, max_length=500)
    source: str = Field(default="", max_length=200)
    conditions: str = Field(default="", max_length=400)

class CompareReq(BaseModel):
    request: SimRequest
    data: ExpData


DEMO = {
    "components": [{"name": "Paracetamol", "mass_mg": 500}, {"name": "Microcrystalline_Cellulose", "mass_mg": 400},
                   {"name": "Croscarmellose_Sodium", "mass_mg": 25}, {"name": "Magnesium_Stearate", "mass_mg": 5}],
    "polymer": "Eudragit_L_100_55", "coating_mass_mg": 46.0, "coating_thickness_mm": 0.10,
    "stages": [{"name": "Stomach (pH 1.2)", "pH": 1.2, "duration_s": 7200, "agitation": 1.5},
               {"name": "Intestine (pH 6.8)", "pH": 6.8, "duration_s": 7200, "agitation": 1.0}],
    "k_base": 0.0005, "dt_s": 2.0,
}


def _build(req: SimRequest):
    core = M.build_core([c.model_dump() for c in req.components])
    coating = poly = None
    if req.polymer and req.coating_mass_mg > 0:
        if req.polymer not in M.POLYMERS: raise SimulationError(f"Unknown polymer '{req.polymer}'.")
        poly = Polymer(req.polymer, **M.POLYMERS[req.polymer])
        coating = Coating(req.coating_mass_mg, 1.0, req.coating_thickness_mm)
    envs = [Environment(s.name, s.pH, s.duration_s, s.agitation) for s in req.stages]
    return core, Core(core["mass"], core["density"], core["solubility"]), coating, poly, envs


def _run_id(req: SimRequest) -> str:
    d = req.model_dump(exclude={"include_band"})
    blob = json.dumps(d, sort_keys=True, separators=(",", ":")) + MODEL_VERSION + M.DATA_VERSION
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _bounds(stages):
    out, t = [], 0.0
    for s in stages: out.append({"name": s.name, "start": t, "end": t + s.duration_s}); t += s.duration_s
    return out


@app.get("/api/health")
def health(): return {"status": "ok", "version": VERSION, "model_version": MODEL_VERSION, "data_version": M.DATA_VERSION}

@app.get("/api/catalog")
def catalog():
    return {"apis": sorted(M.APIS), "excipients": sorted(M.EXCIPIENTS), "polymers": dict(sorted(M.POLYMERS.items())),
            "demo": DEMO, "model_version": MODEL_VERSION, "data_version": M.DATA_VERSION}

@app.get("/api/model")
def model(): return MODEL_INFO


@app.post("/api/simulate")
def run_simulation(req: SimRequest):
    t0 = time.time()
    try:
        core, c, coating, poly, envs = _build(req)
        samp = max(req.dt_s, 10.0)
        res = simulate(c, coating, poly, envs, req.k_base, req.dt_s, samp)
        band = A.band(c, coating, poly, envs, req.k_base, req.dt_s, samp) if req.include_band else None
    except SimulationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        log.exception("simulation failed"); raise HTTPException(status_code=500, detail="Internal simulation error. Please try again.")
    summary = res.summary; first = req.stages[0]
    if first.pH < 4 and coating is not None:
        a = summary["released_pct_at_end_of_stage"][first.name]
        summary["acid_stage_release_pct"] = a; summary["gastric_resistant"] = a <= 10.0
    return {"status": "completed", "run_id": _run_id(req), "model_version": MODEL_VERSION, "data_version": M.DATA_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "request": req.model_dump(),
            "runtime_s": round(time.time() - t0, 3), "core": {k: round(core[k], 4) for k in ("mass", "density", "solubility")},
            "series": res.series, "band": band, "summary": summary, "stage_bounds_s": _bounds(req.stages),
            "storage": M.storage_recommendation(core),
            "disclaimer": "Semi-quantitative model with uncalibrated constants. Not a substitute for laboratory dissolution testing or regulatory evaluation."}


@app.post("/api/compare")
def compare(body: CompareReq):
    d, req = body.data, body.request
    try:
        if len(d.times_min) != len(d.release_pct): raise SimulationError("times_min and release_pct must have the same length.")
        if any(b <= a for a, b in zip(d.times_min, d.times_min[1:])) or d.times_min[0] < 0:
            raise SimulationError("Time values must be >= 0 and strictly increasing.")
        if any(not (0 <= v <= 100) for v in d.release_pct): raise SimulationError("Release values must be within 0-100 %.")
        total = sum(s.duration_s for s in req.stages)
        if d.times_min[-1] * 60 > total: raise SimulationError("Data extends beyond the simulated duration; lengthen the stages.")
        core, c, coating, poly, envs = _build(req)
        samp = max(req.dt_s, 10.0); ts = [m * 60 for m in d.times_min]
        run_k = lambda k: simulate(c, coating, poly, envs, k, req.dt_s, samp).series
        nom = run_k(req.k_base)
        pred = [A.interp(nom, t) for t in ts]
        cal = A.calibrate(run_k, ts, d.release_pct, req.k_base)
    except (SimulationError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"run_id": _run_id(req), "model_version": MODEL_VERSION, "provenance": {"source": d.source, "conditions": d.conditions, "n_points": len(ts)},
            "nominal_model_vs_data": A.metrics(d.release_pct, pred), "nominal_pred": pred, "calibration": cal,
            "notes": ["Only k_base is fitted; film-leak and coating-erosion constants stay uncalibrated.",
                      "Held-out points = every 3rd data point (not used in fitting). This checks interpolation, not extrapolation.",
                      "One dataset cannot validate the model; independent experiments are required."]}


app.mount("/static", StaticFiles(directory=STATIC), name="static")

@app.get("/")
def index(): return FileResponse(STATIC / "index.html")

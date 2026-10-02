"""Projects, formulations, runs, datasets, kinetic fitting, backup/restore (SQLite-backed)."""
import json, re
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Body, Depends, Header
from pydantic import BaseModel, Field
from . import db, dataio, kinetics

def workspace(x_workspace: str = Header(default="")) -> str:
    """Anonymous workspace key (random, created by the client). It isolates data between visitors; it is NOT user authentication."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", x_workspace): raise HTTPException(401, "Missing or invalid X-Workspace header (16-64 letters/digits).")
    return x_workspace


router = APIRouter(prefix="/api", dependencies=[Depends(workspace)])
J = json.dumps


def _404(what): raise HTTPException(404, f"{what} not found.")


def _need(c, pid, ws):
    if not c.execute("SELECT 1 FROM projects WHERE id=? AND workspace=?", (pid, ws)).fetchone(): _404("Project")


MINE = "project_id IN (SELECT id FROM projects WHERE workspace=?)"


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80); notes: str = Field(default="", max_length=4000)

class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80); notes: Optional[str] = Field(default=None, max_length=4000); archived: Optional[bool] = None

class FormIn(BaseModel):
    name: str = Field(min_length=1, max_length=80); body: dict

class RunIn(BaseModel):
    run_id: str = Field(max_length=32); request: dict; summary: dict
    series: list = Field(max_length=2000); model_version: str = Field(default="", max_length=40); data_version: str = Field(default="", max_length=40)

class DatasetPreview(BaseModel):
    csv_text: str

class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80); kind: str = Field(pattern="^(calibration|validation)$")
    csv_text: str; time_col: str; release_col: str
    time_unit: str = "min"; release_unit: str = "percent"
    source: str = Field(default="", max_length=200); conditions: str = Field(default="", max_length=400)

class FitReq(BaseModel):
    dataset_id: str; models: List[str] = Field(min_length=1, max_length=3); validation_dataset_id: Optional[str] = None


# ---- projects ----
@router.get("/projects")
def list_projects(include_archived: bool = False, ws: str = Depends(workspace)):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM projects WHERE workspace=?" + ("" if include_archived else " AND archived=0") + " ORDER BY created", (ws,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["archived"] = bool(d["archived"]); d.pop("workspace", None)
            for t in ("formulations", "runs", "datasets"): d["n_" + t] = c.execute(f"SELECT COUNT(*) FROM {t} WHERE project_id=?", (r["id"],)).fetchone()[0]
            out.append(d)
        return out

@router.post("/projects", status_code=201)
def create_project(p: ProjectIn, ws: str = Depends(workspace)):
    with db.conn() as c:
        pid = db.new_id(); c.execute("INSERT INTO projects VALUES(?,?,?,0,?,?,?)", (pid, p.name, p.notes, db.now(), db.now(), ws))
    return {"id": pid, "name": p.name}

@router.patch("/projects/{pid}")
def patch_project(pid: str, p: ProjectPatch, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws)
        for col, val in (("name", p.name), ("notes", p.notes), ("archived", None if p.archived is None else int(p.archived))):
            if val is not None: c.execute(f"UPDATE projects SET {col}=?, updated=? WHERE id=?", (val, db.now(), pid))
    return {"id": pid, "updated": True}

@router.delete("/projects/{pid}")
def delete_project(pid: str, confirm: bool = False, ws: str = Depends(workspace)):
    if not confirm: raise HTTPException(400, "Deletion requires confirm=true (it removes all formulations, runs and datasets of the project).")
    with db.conn() as c:
        _need(c, pid, ws); c.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"deleted": pid}


# ---- formulations ----
@router.get("/projects/{pid}/formulations")
def list_forms(pid: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws); return [{**dict(r), "body": json.loads(r["body"])} for r in c.execute("SELECT * FROM formulations WHERE project_id=? ORDER BY created", (pid,))]

@router.post("/projects/{pid}/formulations", status_code=201)
def add_form(pid: str, f: FormIn, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws); i = db.new_id(); c.execute("INSERT INTO formulations VALUES(?,?,?,?,?)", (i, pid, f.name, J(f.body), db.now()))
    return {"id": i}

@router.delete("/formulations/{fid}")
def del_form(fid: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        if not c.execute(f"DELETE FROM formulations WHERE id=? AND {MINE}", (fid, ws)).rowcount: _404("Formulation")
    return {"deleted": fid}


# ---- runs ----
@router.get("/projects/{pid}/runs")
def list_runs(pid: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws)
        return [{**dict(r), "request": json.loads(r["request"]), "summary": json.loads(r["summary"]), "series": json.loads(r["series"])}
                for r in c.execute("SELECT * FROM runs WHERE project_id=? ORDER BY created DESC LIMIT 100", (pid,))]

@router.post("/projects/{pid}/runs", status_code=201)
def add_run(pid: str, r: RunIn, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws); c.execute("DELETE FROM runs WHERE project_id=? AND run_id=?", (pid, r.run_id)); i = db.new_id()
        c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)", (i, pid, r.run_id, J(r.request), J(r.summary), J(r.series), r.model_version, r.data_version, db.now()))
    return {"id": i}

@router.delete("/runs/{rid}")
def del_run(rid: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        if not c.execute(f"DELETE FROM runs WHERE id=? AND {MINE}", (rid, ws)).rowcount: _404("Run")
    return {"deleted": rid}


# ---- datasets ----
@router.post("/datasets/preview")
def dataset_preview(d: DatasetPreview):
    try: return dataio.preview(d.csv_text)
    except dataio.DataError as e: raise HTTPException(422, str(e))

@router.post("/projects/{pid}/datasets", status_code=201)
def add_dataset(pid: str, d: DatasetIn, ws: str = Depends(workspace)):
    try: pts, warn = dataio.process(d.csv_text, d.time_col, d.release_col, d.time_unit, d.release_unit)
    except dataio.DataError as e: raise HTTPException(422, str(e))
    with db.conn() as c:
        _need(c, pid, ws); i = db.new_id()
        c.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?,?,?,?,?,?)", (i, pid, d.name, d.kind, d.csv_text, J({"time_col": d.time_col, "release_col": d.release_col, "time_unit": d.time_unit, "release_unit": d.release_unit}),
                  J(pts), d.source, d.conditions, J(warn), db.now()))
    return {"id": i, "n_points": len(pts), "warnings": warn}

@router.get("/projects/{pid}/datasets")
def list_datasets(pid: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        _need(c, pid, ws)
        return [{"id": r["id"], "name": r["name"], "kind": r["kind"], "source": r["source"], "conditions": r["conditions"], "created": r["created"],
                 "n_points": len(json.loads(r["points"])), "warnings": json.loads(r["warnings"])} for r in c.execute("SELECT * FROM datasets WHERE project_id=? ORDER BY created", (pid,))]

@router.get("/datasets/{did}")
def get_dataset(did: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        r = c.execute(f"SELECT * FROM datasets WHERE id=? AND {MINE}", (did, ws)).fetchone()
        if not r: _404("Dataset")
        return {**dict(r), "points": json.loads(r["points"]), "mapping": json.loads(r["mapping"]), "warnings": json.loads(r["warnings"])}

@router.delete("/datasets/{did}")
def del_dataset(did: str, ws: str = Depends(workspace)):
    with db.conn() as c:
        if not c.execute(f"DELETE FROM datasets WHERE id=? AND {MINE}", (did, ws)).rowcount: _404("Dataset")
    return {"deleted": did}


# ---- kinetic fitting (calibration vs independent validation) ----
@router.post("/fit")
def fit_models(q: FitReq, ws: str = Depends(workspace)):
    with db.conn() as c:
        r = c.execute(f"SELECT kind, points FROM datasets WHERE id=? AND {MINE}", (q.dataset_id, ws)).fetchone()
        v = c.execute(f"SELECT kind, points FROM datasets WHERE id=? AND {MINE}", (q.validation_dataset_id, ws)).fetchone() if q.validation_dataset_id else None
    if not r: _404("Dataset")
    if q.validation_dataset_id and not v: _404("Validation dataset")
    if q.validation_dataset_id == q.dataset_id: raise HTTPException(422, "Validation must use a different dataset than calibration.")
    pts = json.loads(r["points"]); out, errs = [], []
    for m in q.models:
        try:
            res = kinetics.fit(m, pts); popt = res.pop("_popt")
            if v: res["validation"] = kinetics.validate(m, popt, json.loads(v["points"]))
            out.append(res)
        except ValueError as e: errs.append(str(e))
    if not out: raise HTTPException(422, "; ".join(errs))
    return {"results": out, "errors": errs, "calibration_dataset_kind": r["kind"],
            "notes": ["Empirical models: parameters describe the curve; they do not prove a release mechanism.",
                      "Uncertainty = asymptotic standard errors / 95 % CI from the fit covariance; unreliable with few points.",
                      "AICc compares models only on the same data and points; R2/RMSE on calibration data are NOT validation.",
                      "Independent validation requires a separate dataset (validation block, if provided)."]}


# ---- backup / restore (own workspace only) ----
@router.get("/backup")
def backup(ws: str = Depends(workspace)):
    with db.conn() as c:
        out = {"format": "astraflux-backup", "version": 1, "created": db.now(),
               "projects": [{k: v for k, v in dict(r).items() if k != "workspace"} for r in c.execute("SELECT * FROM projects WHERE workspace=?", (ws,))]}
        for t in db.TABLES[1:]: out[t] = [dict(r) for r in c.execute(f"SELECT * FROM {t} WHERE {MINE}", (ws,))]
        return out

@router.post("/restore")
def restore(data: dict = Body(...), ws: str = Depends(workspace)):
    if data.get("format") != "astraflux-backup" or data.get("version") != 1: raise HTTPException(422, "Not an AstraFlux backup file (format/version mismatch).")
    if sum(len(data.get(t, [])) for t in db.TABLES) > 20000: raise HTTPException(422, "Backup too large.")
    counts = {}
    with db.conn() as c:
        for t in db.TABLES:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})") if r[1] != "workspace"]
            for row in data.get(t, []):
                if not isinstance(row, dict) or not set(row) <= set(cols): raise HTTPException(422, f"Invalid record in '{t}'.")
                if t == "projects":
                    if c.execute("SELECT 1 FROM projects WHERE id=? AND workspace<>?", (row.get("id"), ws)).fetchone(): raise HTTPException(409, "Project id belongs to another workspace.")
                    row = {**row, "workspace": ws}
                elif not c.execute("SELECT 1 FROM projects WHERE id=? AND workspace=?", (row.get("project_id"), ws)).fetchone() and row.get("project_id") not in {p["id"] for p in data.get("projects", [])}:
                    raise HTTPException(422, f"Record in '{t}' references an unknown project.")
                ks = list(row); c.execute(f"INSERT OR REPLACE INTO {t}({','.join(ks)}) VALUES({','.join('?' * len(ks))})", [row[k] for k in ks]); 
            counts[t] = len(data.get(t, []))
    return {"restored": counts, "mode": "merge into your workspace (same ids overwritten, nothing deleted)"}

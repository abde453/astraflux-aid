---
title: AstraFlux AI
emoji: 💊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# AstraFlux AI — Drug Release Simulator (demo prototype v0.2)

Web prototype that simulates drug release from coated tablets across GI stages (pH, time, agitation),
with a formulation builder, a polymer library (50 polymers) and a heuristic storage suggestion.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn astraflux.api:app --reload                   # open http://localhost:7860
pytest                                               # 41 tests
python postdeploy_check.py http://localhost:7860     # smoke test
```
## Docker
```bash
docker build -t astraflux . && docker run -p 7860:7860 astraflux
```
Layout: `astraflux/` (engine, materials, API, static UI, data) · `tests/` · `docs/` · `legacy/` (original PySide6 desktop tools, kept untouched).
Honest scope: equation-based model, no machine learning / PINN in this version. See `docs/LIMITATIONS_AR.md`.

## Desktop (Windows, offline)
Double-click `build_windows.bat` once (needs Python + internet for the build only). It creates `dist\AstraFluxAI.exe`;
run it to open AstraFlux AI in its own window with no internet and no browser. The server listens on 127.0.0.1 only.
Developer run without building: `python desktop.py`.

## Saved work (database)
Projects, formulations, runs and datasets are stored in SQLite (`~/.astraflux/astraflux.db`, or the path in `ASTRAFLUX_DB`).
Use **Dashboard -> Download backup** regularly. On free cloud hosting (e.g. Hugging Face free tier) the disk is erased on restart:
download a backup first and use **Restore** afterwards. Deleting a project asks for confirmation and removes all of its data.

## Using the API from another site (e.g. Lovable)
Set the Space variables `ALLOWED_ORIGIN_REGEX=https://.*\.(lovable\.app|lovableproject\.com)` (or `ALLOWED_ORIGINS`). See `docs/LOVABLE_API_CONTRACT.md`
and paste `docs/LOVABLE_PROMPT.md` into Lovable. Stored-work endpoints need an `X-Workspace` header (random key per visitor; isolation, not authentication).

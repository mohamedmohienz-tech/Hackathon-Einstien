# FORGE IFC Model Intelligence Server

REST API that queries IFC model files and returns structured 
model data to the FORGE Copilot Studio agent.

## Endpoints

- `GET /model/summary` — full model overview
- `GET /model/elements/{ifc_type}` — elements by type
- `GET /model/storeys` — breakdown by level
- `GET /model/health` — QA health check
- `POST /model/search` — search elements
- `GET /model/properties/{guid}` — element properties
- `POST /model/check/missing-property` — QA property check
- `GET /openapi.json` — FORGE tool configuration

## Run

```bash
pip install flask
python forge_cloudshell.py
```

## Project

WSP ANZ AI Hackathon — 18-19 May 2026  
Greymouth District Court — Project 4-11742

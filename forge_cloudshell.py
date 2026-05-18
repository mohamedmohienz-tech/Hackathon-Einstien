#!/usr/bin/env python3
"""
FORGE IFC Server — GitHub Codespaces Edition
=============================================
A Flask REST API that parses an IFC model with IfcOpenShell
and exposes endpoints Copilot Studio (FORGE) calls as Tools.

Usage in Codespaces:
    pip install flask -q
    python forge_cloudshell.py --ifc "4-11742.01-WSP-M3-01-ST-0001.ifc" --port 5100

Then in the Codespace Ports tab → port 5100 → globe icon → public URL.
That URL + /openapi.json goes into Copilot Studio Tools.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── Globals ──────────────────────────────────────────────────
MODEL = None
IFC_PATH = ""
DEMO_MODE = True

# ── Auto-install ifcopenshell if missing ─────────────────────
try:
    import ifcopenshell
    import ifcopenshell.util.element as ifc_util
    IFC_OK = True
except ImportError:
    print("Installing ifcopenshell...")
    os.system("pip install ifcopenshell -q")
    try:
        import ifcopenshell
        import ifcopenshell.util.element as ifc_util
        IFC_OK = True
        print("ifcopenshell ready")
    except ImportError:
        IFC_OK = False
        print("ifcopenshell unavailable — running in demo mode")


# ─────────────────────────────────────────────────────────────
# IFC LOADING
# ─────────────────────────────────────────────────────────────
def load_ifc(path):
    """Load an IFC file. Returns (success: bool, error: str|None)."""
    global MODEL, IFC_PATH, DEMO_MODE
    if not IFC_OK:
        return False, "ifcopenshell not available"
    p = Path(path)
    if not p.exists():
        return False, f"File not found: {path}"
    try:
        MODEL = ifcopenshell.open(str(p))
        IFC_PATH = str(p)
        DEMO_MODE = False
        return True, None
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def get_psets(el):
    """Return a flat dict of property sets for an element."""
    props = {}
    try:
        psets = ifc_util.get_psets(el)
        for pset_name, pset_data in psets.items():
            for prop_name, value in pset_data.items():
                if prop_name != "id":
                    key = f"{pset_name}.{prop_name}"
                    props[key] = str(value) if value is not None else ""
    except Exception:
        pass
    return props


def get_storey(el):
    """Get the building storey an element belongs to."""
    try:
        container = ifc_util.get_container(el)
        if container and container.is_a("IfcBuildingStorey"):
            return container.Name or "Unnamed Storey"
    except Exception:
        pass
    return "Unassigned"


def element_to_dict(el):
    """Serialise an IFC element to a JSON-safe dict."""
    return {
        "guid": el.GlobalId,
        "type": el.is_a(),
        "name": el.Name or "",
        "tag": getattr(el, "Tag", "") or "",
        "storey": get_storey(el),
        "properties": get_psets(el),
    }


# ─────────────────────────────────────────────────────────────
# DEMO DATA — used when no IFC loaded
# ─────────────────────────────────────────────────────────────
DEMO_SUMMARY = {
    "project_name": "Greymouth District Court (DEMO)",
    "ifc_schema": "IFC4",
    "file_name": "demo.ifc",
    "total_elements": 1247,
    "element_counts": {
        "IfcBeam": 184,
        "IfcColumn": 96,
        "IfcWall": 312,
        "IfcSlab": 78,
        "IfcDoor": 42,
        "IfcWindow": 88,
        "IfcStair": 6,
        "IfcRailing": 24,
    },
    "storeys": ["Ground Floor", "Level 1", "Level 2", "Roof"],
}


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.route("/")
def root():
    return jsonify({
        "service": "FORGE IFC Server",
        "mode": "DEMO" if DEMO_MODE else "LIVE",
        "ifc_loaded": IFC_PATH if not DEMO_MODE else None,
        "endpoints": [
            "/model/summary",
            "/model/elements/<ifc_type>",
            "/model/storeys",
            "/model/health",
            "/model/search (POST)",
            "/model/properties/<guid>",
            "/openapi.json",
        ],
    })


@app.route("/model/summary")
def model_summary():
    """High-level project summary — name, schema, element counts, storeys."""
    if DEMO_MODE or MODEL is None:
        return jsonify(DEMO_SUMMARY)

    project = MODEL.by_type("IfcProject")[0] if MODEL.by_type("IfcProject") else None
    counts = defaultdict(int)
    for el in MODEL.by_type("IfcElement"):
        counts[el.is_a()] += 1

    storeys = [s.Name or f"Storey {i}" for i, s in enumerate(MODEL.by_type("IfcBuildingStorey"))]

    return jsonify({
        "project_name": project.Name if project else "Unknown",
        "ifc_schema": MODEL.schema,
        "file_name": os.path.basename(IFC_PATH),
        "total_elements": sum(counts.values()),
        "element_counts": dict(sorted(counts.items(), key=lambda x: -x[1])),
        "storeys": storeys,
    })


@app.route("/model/elements/<ifc_type>")
def model_elements(ifc_type):
    """List all elements of a given IFC type — e.g. IfcBeam, IfcColumn."""
    if DEMO_MODE or MODEL is None:
        # Return a few sample beams in demo mode
        return jsonify({
            "ifc_type": ifc_type,
            "count": 3,
            "elements": [
                {"guid": "0DEMO1", "type": ifc_type, "name": f"{ifc_type}-001", "storey": "Level 1"},
                {"guid": "0DEMO2", "type": ifc_type, "name": f"{ifc_type}-002", "storey": "Level 1"},
                {"guid": "0DEMO3", "type": ifc_type, "name": f"{ifc_type}-003", "storey": "Level 2"},
            ],
        })

    try:
        elements = MODEL.by_type(ifc_type)
    except Exception as e:
        return jsonify({"error": str(e), "ifc_type": ifc_type}), 400

    return jsonify({
        "ifc_type": ifc_type,
        "count": len(elements),
        "elements": [element_to_dict(el) for el in elements[:200]],  # cap at 200
    })


@app.route("/model/storeys")
def model_storeys():
    """List all building storeys with element counts per storey."""
    if DEMO_MODE or MODEL is None:
        return jsonify({
            "storeys": [
                {"name": "Ground Floor", "element_count": 412},
                {"name": "Level 1", "element_count": 398},
                {"name": "Level 2", "element_count": 287},
                {"name": "Roof", "element_count": 150},
            ]
        })

    storey_counts = defaultdict(int)
    for el in MODEL.by_type("IfcElement"):
        storey_counts[get_storey(el)] += 1

    return jsonify({
        "storeys": [{"name": s, "element_count": c} for s, c in storey_counts.items()]
    })


@app.route("/model/health")
def model_health():
    """Model health checks — missing properties, unclassified elements, etc."""
    if DEMO_MODE or MODEL is None:
        return jsonify({
            "overall_status": "AMBER",
            "checks": [
                {"name": "Elements with names", "status": "GREEN", "score": "1198/1247", "percent": 96},
                {"name": "Elements assigned to storeys", "status": "GREEN", "score": "1247/1247", "percent": 100},
                {"name": "Elements with classification (Uniclass/Omniclass)", "status": "AMBER", "score": "843/1247", "percent": 68},
                {"name": "Elements with material assigned", "status": "AMBER", "score": "1052/1247", "percent": 84},
                {"name": "Elements with fire rating (where required)", "status": "RED", "score": "23/156", "percent": 15},
            ],
        })

    elements = MODEL.by_type("IfcElement")
    total = len(elements) or 1

    with_name = sum(1 for e in elements if e.Name)
    with_storey = sum(1 for e in elements if get_storey(e) != "Unassigned")
    with_psets = sum(1 for e in elements if get_psets(e))

    def status(pct):
        return "GREEN" if pct >= 90 else "AMBER" if pct >= 70 else "RED"

    p_name = round(with_name / total * 100)
    p_storey = round(with_storey / total * 100)
    p_psets = round(with_psets / total * 100)

    overall = "GREEN" if min(p_name, p_storey, p_psets) >= 90 else "AMBER" if min(p_name, p_storey, p_psets) >= 70 else "RED"

    return jsonify({
        "overall_status": overall,
        "checks": [
            {"name": "Elements with names", "status": status(p_name), "score": f"{with_name}/{total}", "percent": p_name},
            {"name": "Elements assigned to storeys", "status": status(p_storey), "score": f"{with_storey}/{total}", "percent": p_storey},
            {"name": "Elements with property sets", "status": status(p_psets), "score": f"{with_psets}/{total}", "percent": p_psets},
        ],
    })


@app.route("/model/search", methods=["POST"])
def model_search():
    """Search elements by name (case-insensitive substring match)."""
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").lower().strip()

    if not query:
        return jsonify({"error": "query field required"}), 400

    if DEMO_MODE or MODEL is None:
        return jsonify({
            "query": query,
            "count": 2,
            "matches": [
                {"guid": "0DEMO1", "type": "IfcBeam", "name": f"Beam containing '{query}'", "storey": "Level 1"},
                {"guid": "0DEMO2", "type": "IfcColumn", "name": f"Column containing '{query}'", "storey": "Level 2"},
            ],
        })

    matches = []
    for el in MODEL.by_type("IfcElement"):
        if el.Name and query in el.Name.lower():
            matches.append(element_to_dict(el))
        if len(matches) >= 100:
            break

    return jsonify({"query": query, "count": len(matches), "matches": matches})


@app.route("/model/properties/<guid>")
def model_properties(guid):
    """Get all properties of a single element by its GUID."""
    if DEMO_MODE or MODEL is None:
        return jsonify({
            "guid": guid,
            "type": "IfcBeam",
            "name": "Demo Beam",
            "properties": {
                "Pset_BeamCommon.LoadBearing": "True",
                "Pset_BeamCommon.IsExternal": "False",
                "Pset_BeamCommon.FireRating": "60min",
            },
        })

    el = MODEL.by_guid(guid)
    if el is None:
        return jsonify({"error": f"No element with GUID {guid}"}), 404

    return jsonify(element_to_dict(el))


# ─────────────────────────────────────────────────────────────
# OPENAPI SPEC — what Copilot Studio reads to register the tools
# ─────────────────────────────────────────────────────────────
@app.route("/openapi.json")
def openapi_spec():
    """OpenAPI 3.0 spec for Copilot Studio Tool registration."""
    host = request.host_url.rstrip("/")
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "FORGE IFC Server",
            "version": "1.0.0",
            "description": "Reads a structural Revit model (exported as IFC) and answers questions about elements, storeys, properties, and model health.",
        },
        "servers": [{"url": host}],
        "paths": {
            "/model/summary": {
                "get": {
                    "operationId": "getModelSummary",
                    "summary": "Get project summary, element counts, schema, and storeys.",
                    "responses": {"200": {"description": "Summary returned"}},
                }
            },
            "/model/elements/{ifc_type}": {
                "get": {
                    "operationId": "getElementsByType",
                    "summary": "List elements of a specific IFC type (IfcBeam, IfcColumn, IfcWall, IfcSlab, etc).",
                    "parameters": [{
                        "name": "ifc_type", "in": "path", "required": True,
                        "schema": {"type": "string"},
                        "description": "IFC class name e.g. IfcBeam",
                    }],
                    "responses": {"200": {"description": "Elements returned"}},
                }
            },
            "/model/storeys": {
                "get": {
                    "operationId": "getStoreys",
                    "summary": "List building storeys with element counts.",
                    "responses": {"200": {"description": "Storeys returned"}},
                }
            },
            "/model/health": {
                "get": {
                    "operationId": "getModelHealth",
                    "summary": "Model health checks — naming completeness, storey assignment, property set coverage. Returns RAG status.",
                    "responses": {"200": {"description": "Health report returned"}},
                }
            },
            "/model/search": {
                "post": {
                    "operationId": "searchElements",
                    "summary": "Search elements by name substring.",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        }}},
                    },
                    "responses": {"200": {"description": "Matches returned"}},
                }
            },
            "/model/properties/{guid}": {
                "get": {
                    "operationId": "getElementProperties",
                    "summary": "Get all properties of a specific element by its IFC GlobalId.",
                    "parameters": [{
                        "name": "guid", "in": "path", "required": True,
                        "schema": {"type": "string"},
                    }],
                    "responses": {"200": {"description": "Properties returned"}},
                }
            },
        },
    }
    return jsonify(spec)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="FORGE IFC Server")
    parser.add_argument("--ifc", help="Path to IFC file. If omitted, runs in demo mode.")
    parser.add_argument("--port", type=int, default=5100, help="Port (default 5100)")
    args = parser.parse_args()

    if args.ifc:
        ok, err = load_ifc(args.ifc)
        if not ok:
            print(f"Failed to load IFC: {err}")
            print("Falling back to DEMO MODE")
        else:
            print(f"Loaded IFC: {args.ifc}")

    mode = "LIVE" if not DEMO_MODE else "DEMO MODE"
    print("=" * 55)
    print(f"FORGE IFC Server [{mode}]")
    print(f"http://localhost:{args.port}")
    print("=" * 55)
    print("  /model/summary")
    print("  /model/elements/IfcBeam  (any IFC type)")
    print("  /model/storeys")
    print("  /model/health")
    print("  /model/search  (POST)")
    print("  /model/properties/<guid>")
    print("  /openapi.json  ← paste into FORGE Tools")
    print("=" * 55)

    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()

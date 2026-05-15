"""FastAPI web app — Cytoscape.js graph visualization + query interface.

Run:
    uv run uvicorn bible_rag.web:app --reload --port 8000

Then open http://localhost:8000
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .db import connect
from . import query as Q


app = FastAPI(title="Bible RAG")

STATIC_DIR = Path(__file__).parent / "static"


# ----- API endpoints -----
@app.get("/api/graph")
def graph() -> dict:
    """Return the full graph as Cytoscape.js elements."""
    conn = connect()
    units = conn.execute(
        "SELECT id, slug, type, title, status, confidence FROM unit"
    ).fetchall()
    edges = conn.execute(
        """
        SELECT c.from_unit, c.to_unit, c.type, c.confidence,
               u1.slug AS from_slug, u2.slug AS to_slug
        FROM connection c
        JOIN unit u1 ON u1.id = c.from_unit
        JOIN unit u2 ON u2.id = c.to_unit
        """
    ).fetchall()
    conn.close()
    nodes = [
        {"data": {"id": u["slug"], "label": u["title"],
                  "type": u["type"], "status": u["status"],
                  "confidence": u["confidence"]}}
        for u in units
    ]
    rels = [
        {"data": {"id": f"{e['from_slug']}->{e['to_slug']}:{e['type']}",
                  "source": e["from_slug"], "target": e["to_slug"],
                  "type": e["type"], "confidence": e["confidence"]}}
        for e in edges
    ]
    return {"elements": {"nodes": nodes, "edges": rels}}


@app.get("/api/unit/{slug:path}")
def unit_detail(slug: str) -> dict:
    conn = connect()
    row = conn.execute(
        "SELECT slug, type, title, status, confidence, body_md FROM unit WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Unit not found: {slug}")
    neighbors_out = Q.neighbors(conn, slug, direction="out")
    neighbors_in = Q.neighbors(conn, slug, direction="in")
    conn.close()
    return {
        "slug": row["slug"], "type": row["type"], "title": row["title"],
        "status": row["status"], "confidence": row["confidence"],
        "body_md": row["body_md"],
        "neighbors_out": [
            {"slug": n["slug"], "title": n["title"], "type": n["type"],
             "edge_type": n["edge_type"]}
            for n in neighbors_out
        ],
        "neighbors_in": [
            {"slug": n["slug"], "title": n["title"], "type": n["type"],
             "edge_type": n["edge_type"]}
            for n in neighbors_in
        ],
    }


@app.get("/api/search")
def search(q: str, limit: int = 10) -> dict:
    if not q.strip():
        return {"results": []}
    conn = connect()
    try:
        rows = Q.fts(conn, q, limit=limit)
        results = [
            {"slug": r["slug"], "type": r["type"], "title": r["title"],
             "snippet": r["snippet"]}
            for r in rows
        ]
    finally:
        conn.close()
    return {"results": results}


@app.get("/api/hubs")
def hubs(top_n: int = 15) -> dict:
    conn = connect()
    rows = Q.hubs(conn, top_n=top_n)
    conn.close()
    return {
        "hubs": [
            {"slug": r["slug"], "type": r["type"], "title": r["title"],
             "degree": r["degree"]}
            for r in rows
        ]
    }


# ----- Static frontend -----
@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/3d", response_class=HTMLResponse)
def three_d() -> FileResponse:
    """Alternative 3D force-directed graph visualization."""
    return FileResponse(STATIC_DIR / "3d.html")


# Mount static after the routes that take precedence
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

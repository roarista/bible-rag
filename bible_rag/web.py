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
# PaRDeS hermeneutic layering — each connection type lives at one of four
# interpretive depths from classical Jewish exegesis:
#   peshat  — plain / literal (citations, geographic refs, named-person links)
#   remez   — hint / allegorical (symbol, motif, lexical echo)
#   derash  — comparative / midrashic (rabbinic & church-tradition links)
#   sod     — mystical / typological (foreshadows, fulfills, deep echoes)
PARDES_BY_EDGE_TYPE = {
    # peshat — what the text literally says
    "references": "peshat",
    "references_person": "peshat",
    "references_place": "peshat",
    "references_number": "peshat",
    "references_title": "peshat",
    "cites": "peshat",
    # remez — hidden hints in vocabulary and imagery
    "uses_symbol": "remez",
    "has_motif": "remez",
    "shares_lexeme": "remez",
    "lexical_echo": "remez",
    "discovered_echo": "remez",
    "offset_echo": "remez",
    # derash — comparative tradition (rabbinic + churchy cross-readings)
    "sefaria_reference": "derash",
    "sefaria_related": "derash",
    "sefaria_commentary": "derash",
    "sefaria_midrash": "derash",
    "sefaria_quotation": "derash",
    "sefaria_sifrei_mitzvot": "derash",
    "sefaria_mesorat_hashas": "derash",
    "parallels": "derash",
    # sod — typological / mystical / canonical-fulfillment
    "foreshadows": "sod",
    "fulfills": "sod",
    "personal_link": "sod",
}


def pardes_for(edge_type: str, score: float | None = None) -> str:
    """High-score remez/derash echoes (≥0.85) get promoted to `sod` — at that
    confidence they're effectively asserting typology, not merely hinting."""
    base = PARDES_BY_EDGE_TYPE.get(edge_type, "remez")
    if score is not None and score >= 0.85 and base in {"remez", "derash"}:
        return "sod"
    return base


@app.get("/api/graph")
def graph(include_lexeme: bool = False, pardes: str | None = None) -> dict:
    """Return the full graph as Cytoscape.js elements.

    `shares_lexeme` edges (50k+) are excluded by default — the viz can't render
    them legibly. Pass `?include_lexeme=true` to include them.

    `pardes` is a comma-separated subset of {peshat, remez, derash, sod}. When
    set, only edges whose type maps into that subset are returned.
    """
    conn = connect()
    units = conn.execute(
        "SELECT id, slug, type, title, status, confidence FROM unit"
    ).fetchall()
    # By default: include all typed edges + only PROMOTED shares_lexeme.
    # ?include_lexeme=true returns every shares_lexeme edge (including noise).
    if include_lexeme:
        where = ""
    else:
        where = ("WHERE c.type != 'shares_lexeme' "
                 "OR c.score_status = 'promoted'")
    edges = conn.execute(
        f"""
        SELECT c.from_unit, c.to_unit, c.type, c.confidence, c.score,
               u1.slug AS from_slug, u2.slug AS to_slug
        FROM connection c
        JOIN unit u1 ON u1.id = c.from_unit
        JOIN unit u2 ON u2.id = c.to_unit
        {where}
        """
    ).fetchall()
    conn.close()
    nodes = [
        {"data": {"id": u["slug"], "label": u["title"],
                  "type": u["type"], "status": u["status"],
                  "confidence": u["confidence"]}}
        for u in units
    ]
    pardes_filter = None
    if pardes:
        pardes_filter = {p.strip() for p in pardes.split(",") if p.strip()}
    rels = []
    for e in edges:
        layer = pardes_for(e["type"], e["score"])
        if pardes_filter and layer not in pardes_filter:
            continue
        rels.append({"data": {
            "id": f"{e['from_slug']}->{e['to_slug']}:{e['type']}",
            "source": e["from_slug"], "target": e["to_slug"],
            "type": e["type"], "confidence": e["confidence"],
            "score": e["score"], "pardes": layer,
        }})
    return {"elements": {"nodes": nodes, "edges": rels}}


@app.get("/api/unit/{slug:path}")
def unit_detail(slug: str) -> dict:
    import json as _json
    conn = connect()
    row = conn.execute(
        "SELECT slug, type, title, status, confidence, body_md, frontmatter "
        "FROM unit WHERE slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Unit not found: {slug}")
    neighbors_out = Q.neighbors(conn, slug, direction="out")
    neighbors_in = Q.neighbors(conn, slug, direction="in")
    conn.close()
    theographic = None
    try:
        fm = _json.loads(row["frontmatter"]) if row["frontmatter"] else {}
        theographic = fm.get("theographic")
    except _json.JSONDecodeError:
        pass
    return {
        "slug": row["slug"], "type": row["type"], "title": row["title"],
        "status": row["status"], "confidence": row["confidence"],
        "body_md": row["body_md"],
        "theographic": theographic,
        "neighbors_out": [
            {"slug": n["slug"], "title": n["title"], "type": n["type"],
             "edge_type": n["edge_type"], "score": n["edge_score"],
             "rationale": n["edge_rationale"], "edge_status": n["edge_status"]}
            for n in neighbors_out
        ],
        "neighbors_in": [
            {"slug": n["slug"], "title": n["title"], "type": n["type"],
             "edge_type": n["edge_type"], "score": n["edge_score"],
             "rationale": n["edge_rationale"], "edge_status": n["edge_status"]}
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

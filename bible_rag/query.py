"""Query interface for the Bible RAG.

Three flavors of query:
  • graph traversals — typed walks across `connection`
  • full-text search — over unit body content (FTS5)
  • semantic similarity — nearest neighbors in embedding space (sqlite-vec)
"""

import sqlite3
import struct
from typing import Iterable

from .embedder import MODEL, vector_to_blob, get_client


# ----------------------------------------------------------------------
# Graph queries
# ----------------------------------------------------------------------
def neighbors(conn: sqlite3.Connection, slug: str,
              edge_type: str | None = None, direction: str = "out") -> list[sqlite3.Row]:
    """Return units one hop away from the given unit."""
    if direction == "out":
        sql = """
        SELECT u.*, c.type AS edge_type, c.confidence AS edge_confidence,
               c.score AS edge_score, c.score_rationale AS edge_rationale,
               c.score_status AS edge_status
        FROM connection c
        JOIN unit u  ON u.id = c.to_unit
        JOIN unit u0 ON u0.id = c.from_unit
        WHERE u0.slug = ?
        """
    else:
        sql = """
        SELECT u.*, c.type AS edge_type, c.confidence AS edge_confidence,
               c.score AS edge_score, c.score_rationale AS edge_rationale,
               c.score_status AS edge_status
        FROM connection c
        JOIN unit u  ON u.id = c.from_unit
        JOIN unit u0 ON u0.id = c.to_unit
        WHERE u0.slug = ?
        """
    params: list = [slug]
    if edge_type:
        sql += " AND c.type = ?"
        params.append(edge_type)
    # Hide rejected/noise edges by default — they would flood the neighbor list.
    sql += (" AND (c.score_status IS NULL OR c.score_status NOT IN "
            "('rejected_prefilter','noise'))")
    sql += " ORDER BY COALESCE(c.score, c.confidence) DESC, u.title"
    return conn.execute(sql, params).fetchall()


def seeds_sharing_symbol(conn: sqlite3.Connection, symbol_slug: str) -> list[sqlite3.Row]:
    """All seeds that link to a given symbol."""
    return conn.execute(
        """
        SELECT u.* FROM unit u
        JOIN connection c ON c.from_unit = u.id
        JOIN unit s ON s.id = c.to_unit
        WHERE s.slug = ? AND c.type = 'uses_symbol' AND u.type = 'seed'
        ORDER BY u.title
        """,
        (symbol_slug,),
    ).fetchall()


def hubs(conn: sqlite3.Connection, top_n: int = 10) -> list[sqlite3.Row]:
    """Most-connected units — the hubs of the graph."""
    return conn.execute(
        """
        SELECT u.slug, u.type, u.title, COUNT(c.id) AS degree
        FROM unit u
        LEFT JOIN connection c
          ON c.from_unit = u.id OR c.to_unit = u.id
        GROUP BY u.id
        ORDER BY degree DESC, u.title
        LIMIT ?
        """,
        (top_n,),
    ).fetchall()


# ----------------------------------------------------------------------
# Full-text search
# ----------------------------------------------------------------------
def fts(conn: sqlite3.Connection, query: str, limit: int = 10) -> list[sqlite3.Row]:
    """FTS5 search over unit titles and bodies."""
    return conn.execute(
        """
        SELECT u.slug, u.type, u.title,
               snippet(unit_fts, 1, '<<', '>>', '...', 24) AS snippet
        FROM unit_fts
        JOIN unit u ON u.id = unit_fts.rowid
        WHERE unit_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()


# ----------------------------------------------------------------------
# Semantic similarity
# ----------------------------------------------------------------------
def similar_to_unit(conn: sqlite3.Connection, slug: str, k: int = 5,
                    model: str = MODEL) -> list[sqlite3.Row]:
    """Find k most semantically similar units to a given unit."""
    seed_emb = conn.execute(
        """
        SELECT v.vector FROM embedding_vec v
        JOIN embedding_meta m ON m.id = v.embedding_id
        JOIN unit u ON u.id = m.unit_id
        WHERE u.slug = ? AND m.model = ?
        """,
        (slug, model),
    ).fetchone()
    if not seed_emb:
        raise ValueError(f"No embedding for {slug!r} with model {model}")
    return _knn_from_vector_blob(conn, seed_emb["vector"], k, exclude_slug=slug)


def similar_to_text(conn: sqlite3.Connection, text: str, k: int = 5,
                    model: str = MODEL) -> list[sqlite3.Row]:
    """Embed arbitrary text and find k most similar units."""
    client = get_client()
    vec = client.embeddings.create(model=model, input=text).data[0].embedding
    return _knn_from_vector_blob(conn, vector_to_blob(vec), k)


def _knn_from_vector_blob(conn: sqlite3.Connection, qvec_blob: bytes, k: int,
                          exclude_slug: str | None = None) -> list[sqlite3.Row]:
    extra = "AND u.slug != ?" if exclude_slug else ""
    params: list = [qvec_blob, k + (1 if exclude_slug else 0)]
    if exclude_slug:
        params.append(exclude_slug)
    rows = conn.execute(
        f"""
        SELECT u.slug, u.type, u.title, vec.distance
        FROM embedding_vec vec
        JOIN embedding_meta m ON m.id = vec.embedding_id
        JOIN unit u ON u.id = m.unit_id
        WHERE vec.vector MATCH ?
          AND vec.k = ?
          {extra}
        ORDER BY vec.distance
        """,
        params,
    ).fetchall()
    if exclude_slug:
        rows = [r for r in rows if r["slug"] != exclude_slug][:k]
    return rows

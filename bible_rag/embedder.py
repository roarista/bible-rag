"""Embed units with OpenAI text-embedding-3-large.

Each unit is embedded at one scale ('seed' for typology entries, 'symbol'/'motif'
for the conceptual hubs). The input text combines title + body so structural
context and semantic content are both captured.

Run after `importer.import_all`. Idempotent — skips units already embedded
with the same model+scale.
"""

import os
import sqlite3
import struct
from typing import Iterable

from openai import OpenAI


MODEL = "text-embedding-3-large"


def get_client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set.  Add it to your shell:\n"
            "  echo 'export OPENAI_API_KEY=sk-...' >> ~/.zshrc && source ~/.zshrc"
        )
    return OpenAI(api_key=key)


def vector_to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def units_to_embed(conn: sqlite3.Connection, model: str = MODEL) -> Iterable[sqlite3.Row]:
    """Return units that don't yet have an embedding for this model."""
    return conn.execute(
        """
        SELECT u.id, u.type, u.slug, u.title, u.body_md
        FROM unit u
        LEFT JOIN embedding_meta e
          ON e.unit_id = u.id AND e.model = ?
        WHERE e.id IS NULL
        ORDER BY u.id
        """,
        (model,),
    )


def build_input_text(unit_type: str, title: str, body: str) -> str:
    """Compose the input text for embedding. Title gets emphasis; body capped."""
    body_trimmed = body.strip()[:6000]
    return f"[{unit_type}] {title}\n\n{body_trimmed}"


def embed_units(conn: sqlite3.Connection, model: str = MODEL, dry_run: bool = False) -> dict:
    """Embed all unembedded units. Returns count + estimated cost."""
    pending = list(units_to_embed(conn, model))
    if not pending:
        return {"embedded": 0, "skipped": "all units already embedded"}

    if dry_run:
        return {"would_embed": len(pending),
                "estimated_tokens": sum(len(u["body_md"] or "") // 3 for u in pending)}

    client = get_client()
    embedded = 0
    for row in pending:
        scale = row["type"]  # 'seed' / 'symbol' / 'motif'
        input_text = build_input_text(row["type"], row["title"], row["body_md"] or "")

        resp = client.embeddings.create(model=model, input=input_text)
        vec = resp.data[0].embedding

        cur = conn.execute(
            """
            INSERT INTO embedding_meta (unit_id, model, scale, input_text)
            VALUES (?, ?, ?, ?)
            RETURNING id
            """,
            (row["id"], model, scale, input_text),
        )
        emb_id = cur.fetchone()[0]

        conn.execute(
            "INSERT INTO embedding_vec (embedding_id, vector) VALUES (?, ?)",
            (emb_id, vector_to_blob(vec)),
        )
        conn.commit()
        embedded += 1

    return {"embedded": embedded, "model": model}

"""Render the 2000 candidate edges into 5 self-contained JSONL batches.

Each line is one edge with full context so the scoring agent doesn't need DB
access at scoring time. Batches are written to data/scoring/batch_{1..5}.jsonl.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402


OUT = Path("data/scoring")
OUT.mkdir(parents=True, exist_ok=True)
N_BATCHES = 5


def snippet(s: str | None, n: int = 240) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    return s[:n] + ("…" if len(s) > n else "")


def lexeme_info(cur, strongs: str) -> dict:
    """Look up gloss/lemma/transliteration for a Strong's number."""
    if strongs.startswith("H"):
        r = cur.execute(
            "SELECT lemma, transliteration, gloss FROM macula_hebrew_token "
            "WHERE strongs=? LIMIT 1", (strongs,)
        ).fetchone()
        if r:
            return {"lemma": r["lemma"], "translit": r["transliteration"], "gloss": r["gloss"]}
        r = cur.execute(
            "SELECT hebrew_lemma AS lemma, transliteration AS translit, brief_meaning AS gloss "
            "FROM stepbible_lex_hebrew WHERE strongs=? LIMIT 1", (strongs,)
        ).fetchone()
        if r:
            return {"lemma": r["lemma"], "translit": r["translit"], "gloss": r["gloss"]}
    elif strongs.startswith("G"):
        r = cur.execute(
            "SELECT lemma, gloss FROM macula_greek_token WHERE strongs=? LIMIT 1",
            (strongs,)
        ).fetchone()
        if r:
            return {"lemma": r["lemma"], "translit": None, "gloss": r["gloss"]}
        r = cur.execute(
            "SELECT greek_lemma AS lemma, transliteration AS translit, brief_meaning AS gloss "
            "FROM stepbible_lex_greek WHERE strongs=? LIMIT 1", (strongs,)
        ).fetchone()
        if r:
            return {"lemma": r["lemma"], "translit": r["translit"], "gloss": r["gloss"]}
    return {}


def main() -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT c.id, c.from_unit, c.to_unit, c.evidence_md, "
        "u1.slug AS from_slug, u1.type AS from_type, u1.title AS from_title, u1.body_md AS from_body, "
        "u2.slug AS to_slug,   u2.type AS to_type,   u2.title AS to_title,   u2.body_md AS to_body "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.score_status='candidate' "
        "ORDER BY c.id"
    )
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} candidate edges")

    # Lexeme freq for context
    heb_freq = dict(cur.execute("SELECT strongs, COUNT(*) FROM macula_hebrew_token WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs").fetchall())
    grk_freq = dict(cur.execute("SELECT strongs, COUNT(*) FROM macula_greek_token  WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs").fetchall())

    batch_files = [OUT / f"batch_{i+1}.jsonl" for i in range(N_BATCHES)]
    handles = [open(f, "w", encoding="utf-8") for f in batch_files]

    for idx, r in enumerate(rows):
        strongs = (r["evidence_md"] or "").split(":")[-1].strip()
        info = lexeme_info(cur, strongs) if strongs else {}
        freq = heb_freq.get(strongs) or grk_freq.get(strongs)
        record = {
            "edge_id": r["id"],
            "from": {"slug": r["from_slug"], "type": r["from_type"],
                     "title": r["from_title"], "body": snippet(r["from_body"])},
            "to":   {"slug": r["to_slug"],   "type": r["to_type"],
                     "title": r["to_title"],   "body": snippet(r["to_body"])},
            "shared": {
                "strongs": strongs,
                "lemma": info.get("lemma"),
                "translit": info.get("translit"),
                "gloss": info.get("gloss"),
                "global_freq": freq,
            },
        }
        handles[idx % N_BATCHES].write(json.dumps(record, ensure_ascii=False) + "\n")

    for h in handles:
        h.close()
    for f in batch_files:
        n = sum(1 for _ in open(f))
        print(f"  {f.name}: {n} edges")


if __name__ == "__main__":
    main()

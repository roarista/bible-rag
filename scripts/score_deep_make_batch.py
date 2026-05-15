"""Render the 179 promoted lexeme edges into a single deep-pass batch.

Each line is far richer than the first pass: includes both unit bodies
in full (not just snippets), the lexeme's Strong's number and gloss, all
verses where the lexeme occurs (Hebrew + Greek), and any prior scoring
data so the agent can audit the original heuristic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

OUT = Path("data/scoring/deep_batch.jsonl")
OUT.parent.mkdir(parents=True, exist_ok=True)


def verse_refs_for_lexeme(cur, strongs: str, limit: int = 20) -> list[str]:
    if strongs.startswith("H"):
        rows = cur.execute(
            "SELECT DISTINCT book, chapter, verse FROM macula_hebrew_token "
            "WHERE strongs=? LIMIT ?", (strongs, limit)
        ).fetchall()
    elif strongs.startswith("G"):
        rows = cur.execute(
            "SELECT DISTINCT book, chapter, verse FROM macula_greek_token "
            "WHERE strongs=? LIMIT ?", (strongs, limit)
        ).fetchall()
    else:
        return []
    return [f"{r['book']} {r['chapter']}:{r['verse']}" for r in rows]


def lex_meta(cur, strongs: str) -> dict:
    if strongs.startswith("H"):
        r = cur.execute(
            "SELECT lemma, transliteration, gloss FROM macula_hebrew_token "
            "WHERE strongs=? LIMIT 1", (strongs,)
        ).fetchone()
        if r:
            return dict(r)
    elif strongs.startswith("G"):
        r = cur.execute(
            "SELECT lemma, gloss FROM macula_greek_token "
            "WHERE strongs=? LIMIT 1", (strongs,)
        ).fetchone()
        if r:
            return dict(r)
    return {}


def main() -> None:
    conn = connect()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT c.id, c.from_unit, c.to_unit, c.evidence_md, c.score, c.score_rationale, "
        "u1.slug AS from_slug, u1.type AS from_type, u1.title AS from_title, u1.body_md AS from_body, "
        "u2.slug AS to_slug,   u2.type AS to_type,   u2.title AS to_title,   u2.body_md AS to_body "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='shares_lexeme' AND c.score_status='promoted' "
        "ORDER BY c.score DESC"
    ).fetchall()
    print(f"Loaded {len(rows)} promoted edges for deep rescore")

    with open(OUT, "w", encoding="utf-8") as out:
        for r in rows:
            strongs = (r["evidence_md"] or "").split(":")[-1].strip()
            meta = lex_meta(cur, strongs)
            occurrences = verse_refs_for_lexeme(cur, strongs, limit=12)
            record = {
                "edge_id": r["id"],
                "prior_score": r["score"],
                "prior_rationale": r["score_rationale"],
                "from": {"slug": r["from_slug"], "type": r["from_type"],
                         "title": r["from_title"],
                         "body": " ".join((r["from_body"] or "").split())[:1500]},
                "to":   {"slug": r["to_slug"], "type": r["to_type"],
                         "title": r["to_title"],
                         "body": " ".join((r["to_body"] or "").split())[:1500]},
                "shared": {
                    "strongs": strongs,
                    "lemma": meta.get("lemma"),
                    "translit": meta.get("transliteration"),
                    "gloss": meta.get("gloss"),
                    "occurrences": occurrences,
                },
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

"""Render the unscored sefaria-derived edges into 5 batches for parallel scoring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

OUT = Path("data/scoring")
OUT.mkdir(parents=True, exist_ok=True)
N_BATCHES = 5


def snippet(s: str | None, n: int = 350) -> str:
    if not s:
        return ""
    s = " ".join(s.split())
    return s[:n] + ("…" if len(s) > n else "")


def main() -> None:
    conn = connect()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT c.id, c.type, "
        "u1.slug AS from_slug, u1.type AS from_type, u1.title AS from_title, u1.body_md AS from_body, "
        "u2.slug AS to_slug,   u2.type AS to_type,   u2.title AS to_title,   u2.body_md AS to_body "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type LIKE 'sefaria_%' AND c.score IS NULL "
        "ORDER BY c.id"
    ).fetchall()
    print(f"Loaded {len(rows)} sefaria edges to score")

    handles = [open(OUT / f"sefaria_batch_{i+1}.jsonl", "w", encoding="utf-8")
               for i in range(N_BATCHES)]
    for idx, r in enumerate(rows):
        record = {
            "edge_id": r["id"],
            "sefaria_link_type": r["type"].replace("sefaria_", ""),
            "from": {"slug": r["from_slug"], "type": r["from_type"],
                     "title": r["from_title"], "body": snippet(r["from_body"])},
            "to":   {"slug": r["to_slug"], "type": r["to_type"],
                     "title": r["to_title"], "body": snippet(r["to_body"])},
        }
        handles[idx % N_BATCHES].write(json.dumps(record, ensure_ascii=False) + "\n")
    for h in handles:
        h.close()
    for i in range(N_BATCHES):
        p = OUT / f"sefaria_batch_{i+1}.jsonl"
        n = sum(1 for _ in open(p))
        print(f"  {p.name}: {n} edges")


if __name__ == "__main__":
    main()

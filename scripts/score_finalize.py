"""Consume the 5 scored JSONL files and write back to the DB.

Sets score + score_rationale on each edge and updates score_status:
  - score >= 0.55  → 'promoted'  (worth surfacing as a discovered echo)
  - score <  0.55  → 'noise'
Edges that weren't candidates (rejected_prefilter) are left alone.

Also prints a coverage + distribution report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402


THRESHOLD = 0.55
SCORES_DIR = Path("data/scoring")


def main() -> None:
    rows: list[tuple[int, float, str]] = []
    for i in range(1, 6):
        path = SCORES_DIR / f"scores_{i}.jsonl"
        if not path.exists():
            print(f"  MISSING: {path}")
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                eid = r.get("edge_id")
                sc = r.get("score")
                ra = r.get("rationale", "")
                if eid is None or sc is None:
                    continue
                rows.append((int(eid), float(sc), str(ra)))
        n = sum(1 for _ in open(path))
        print(f"  {path.name}: {n} lines")

    print(f"\nTotal scored: {len(rows)}")
    if not rows:
        return

    conn = connect()
    cur = conn.cursor()
    for eid, sc, ra in rows:
        status = "promoted" if sc >= THRESHOLD else "noise"
        cur.execute(
            "UPDATE connection SET score=?, score_rationale=?, score_status=? WHERE id=?",
            (sc, ra, status, eid),
        )
    conn.commit()

    # Distribution report
    buckets = [(0.0, 0.3), (0.3, 0.55), (0.55, 0.85), (0.85, 1.01)]
    print("\nScore distribution (after applying threshold):")
    for lo, hi in buckets:
        n = cur.execute(
            "SELECT COUNT(*) c FROM connection "
            "WHERE type='shares_lexeme' AND score >= ? AND score < ?",
            (lo, hi),
        ).fetchone()["c"]
        print(f"  [{lo:.2f}-{hi:.2f}): {n}")

    promoted = cur.execute(
        "SELECT COUNT(*) c FROM connection "
        "WHERE type='shares_lexeme' AND score_status='promoted'"
    ).fetchone()["c"]
    print(f"\nPromoted: {promoted}")

    # Top 15 promoted edges
    print("\nTop 15 promoted echoes:")
    top = cur.execute(
        "SELECT c.score, u1.title AS a, u2.title AS b, c.evidence_md, c.score_rationale "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='shares_lexeme' AND c.score_status='promoted' "
        "ORDER BY c.score DESC LIMIT 15"
    ).fetchall()
    for r in top:
        print(f"  {r['score']:.2f}  {r['a']} ↔ {r['b']}  ({r['evidence_md']})")
        print(f"        → {r['score_rationale']}")
    conn.close()


if __name__ == "__main__":
    main()

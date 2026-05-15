"""Merge sefaria_scores_{1..5}.jsonl into the connection table.

Threshold: score >= 0.55 → score_status='promoted', else 'noise'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

THRESHOLD = 0.55
DIR = Path("data/scoring")


def main() -> None:
    rows: list[tuple[int, float, str]] = []
    for i in range(1, 6):
        p = DIR / f"sefaria_scores_{i}.jsonl"
        if not p.exists():
            print(f"  MISSING: {p}")
            continue
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append((int(r["edge_id"]), float(r["score"]),
                             str(r.get("rationale", ""))))
        print(f"  {p.name}: {sum(1 for _ in open(p))} lines")

    print(f"\nTotal: {len(rows)}")
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

    # Distribution
    buckets = [(0.0, 0.3), (0.3, 0.55), (0.55, 0.85), (0.85, 1.01)]
    print("\nSefaria score distribution:")
    for lo, hi in buckets:
        n = cur.execute(
            "SELECT COUNT(*) c FROM connection "
            "WHERE type LIKE 'sefaria_%' AND score >= ? AND score < ?",
            (lo, hi),
        ).fetchone()["c"]
        print(f"  [{lo:.2f}-{hi:.2f}): {n}")

    promoted = cur.execute(
        "SELECT COUNT(*) c FROM connection "
        "WHERE type LIKE 'sefaria_%' AND score_status='promoted'"
    ).fetchone()["c"]
    print(f"\nPromoted: {promoted}")

    print("\nTop 15 sefaria echoes:")
    top = cur.execute(
        "SELECT c.score, c.type, u1.title AS a, u2.title AS b, c.score_rationale "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type LIKE 'sefaria_%' AND c.score_status='promoted' "
        "ORDER BY c.score DESC LIMIT 15"
    ).fetchall()
    for r in top:
        print(f"  {r['score']:.2f}  [{r['type']}]  {r['a']} ↔ {r['b']}")
        print(f"        → {r['score_rationale']}")
    conn.close()


if __name__ == "__main__":
    main()

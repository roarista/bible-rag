"""Apply discovery_scores_{1..5}.jsonl to the discovered_echo edges in DB.
Threshold: score >= 0.65 → 'promoted', else 'noise'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

THRESHOLD = 0.65
DIR = Path("data/scoring")


def main() -> None:
    rows: list[tuple[int, float, str]] = []
    for i in range(1, 6):
        p = DIR / f"discovery_scores_{i}.jsonl"
        if not p.exists():
            continue
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                rows.append((int(r["edge_id"]), float(r["score"]),
                             str(r.get("rationale", ""))))
        print(f"  {p.name}: {sum(1 for _ in open(p))} lines")

    print(f"\nTotal: {len(rows)}")
    conn = connect()
    cur = conn.cursor()
    for eid, sc, ra in rows:
        status = "promoted" if sc >= THRESHOLD else "noise"
        cur.execute(
            "UPDATE connection SET score=?, score_rationale=?, score_status=? WHERE id=?",
            (sc, ra, status, eid),
        )
    conn.commit()

    promoted = cur.execute(
        "SELECT COUNT(*) c FROM connection WHERE type='discovered_echo' AND score_status='promoted'"
    ).fetchone()["c"]
    print(f"\nPromoted (≥{THRESHOLD}): {promoted}")

    print("\nTop 20 discovered echoes:")
    for r in cur.execute(
        "SELECT c.score, u1.type AS ta, u1.title AS a, u2.type AS tb, u2.title AS b, c.score_rationale "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='discovered_echo' AND c.score_status='promoted' "
        "ORDER BY c.score DESC LIMIT 20"
    ).fetchall():
        print(f"  {r['score']:.2f}  [{r['ta']}/{r['tb']}]  {r['a']} ↔ {r['b']}")
        print(f"        → {r['score_rationale']}")
    conn.close()


if __name__ == "__main__":
    main()

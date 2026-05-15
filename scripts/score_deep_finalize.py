"""Apply deep_scores.jsonl (second-pass scores for the 179 promoted lexeme edges)
back to the connection table. Demotions move edges to score_status='noise'.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

THRESHOLD = 0.55
INPUT = Path("data/scoring/deep_scores.jsonl")


def main() -> None:
    conn = connect()
    cur = conn.cursor()

    rows: list[tuple[int, float, str]] = []
    with open(INPUT) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append((int(r["edge_id"]), float(r["score"]),
                         str(r.get("rationale", ""))))
    print(f"Loaded {len(rows)} deep scores")

    upgrades = 0
    demotions = 0
    for eid, sc, ra in rows:
        prior = cur.execute(
            "SELECT score FROM connection WHERE id=?", (eid,)
        ).fetchone()
        prior_sc = prior["score"] or 0.0
        status = "promoted" if sc >= THRESHOLD else "noise"
        cur.execute(
            "UPDATE connection SET score=?, score_rationale=?, score_status=? WHERE id=?",
            (sc, ra, status, eid),
        )
        if sc > prior_sc + 0.05:
            upgrades += 1
        elif sc < prior_sc - 0.05:
            demotions += 1
    conn.commit()

    print(f"\nUpgrades (+0.05 or more): {upgrades}")
    print(f"Demotions (-0.05 or more): {demotions}")

    buckets = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]
    print("\nDeep-rescored distribution:")
    for lo, hi in buckets:
        n = cur.execute(
            "SELECT COUNT(*) c FROM connection "
            "WHERE type='shares_lexeme' AND score >= ? AND score < ?",
            (lo, hi),
        ).fetchone()["c"]
        print(f"  [{lo:.2f}-{hi:.2f}): {n}")

    print("\nTop 20 deep-rescored echoes (≥0.85):")
    top = cur.execute(
        "SELECT c.score, u1.title AS a, u2.title AS b, c.evidence_md, c.score_rationale "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='shares_lexeme' AND c.score >= 0.85 "
        "ORDER BY c.score DESC LIMIT 20"
    ).fetchall()
    for r in top:
        print(f"  {r['score']:.2f}  {r['a']} ↔ {r['b']}  ({r['evidence_md']})")
        print(f"        → {r['score_rationale']}")
    conn.close()


if __name__ == "__main__":
    main()

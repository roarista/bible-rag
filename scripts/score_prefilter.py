"""Deterministic prefilter for shares_lexeme edges.

Picks the top N most-promising candidates for LLM scoring, using:
  - rarity weight (1/global_freq of the shared Strong's)
  - novelty bonus (no other typed edge between the same units)
  - type-pair sanity (skip edges where BOTH units are themselves of type='lexeme';
    the connection there is trivial)
  - per-lexeme cap (avoid one super-rare word dominating)

Marks the picked edges with score_status='candidate'; everything else
remains score_status=NULL (rejected at prefilter, will be hidden from the
discovered-edge view but kept in DB for completeness).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402


TOP_N = 2000
PER_LEXEME_CAP = 8


def main() -> None:
    conn = connect()
    cur = conn.cursor()

    # Lexeme frequencies (already computed in cross_link; recompute here to be
    # self-contained).
    heb_freq = dict(cur.execute(
        "SELECT strongs, COUNT(*) FROM macula_hebrew_token "
        "WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs"
    ).fetchall())
    grk_freq = dict(cur.execute(
        "SELECT strongs, COUNT(*) FROM macula_greek_token "
        "WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs"
    ).fetchall())

    def freq(strongs: str) -> int:
        return heb_freq.get(strongs) or grk_freq.get(strongs) or 1

    # Build set of (a,b) pairs that have *some other* typed edge between them.
    print("Indexing existing non-lexeme edges between unit pairs…")
    other_edges: set[tuple[int, int]] = set()
    for r in cur.execute(
        "SELECT from_unit, to_unit FROM connection WHERE type != 'shares_lexeme'"
    ):
        a, b = sorted((r["from_unit"], r["to_unit"]))
        other_edges.add((a, b))

    # Map from_unit/to_unit → unit type, to skip lexeme-lexeme edges.
    type_by_id = {r["id"]: r["type"] for r in cur.execute("SELECT id, type FROM unit")}

    print("Loading shares_lexeme edges…")
    rows = cur.execute(
        "SELECT id, from_unit, to_unit, evidence_md FROM connection "
        "WHERE type='shares_lexeme'"
    ).fetchall()
    print(f"  {len(rows)} edges to rank")

    scored: list[tuple[float, int, str]] = []  # (rank_score, edge_id, strongs)
    for r in rows:
        # Strongs lives in evidence_md: "Shared rare Strong's: H2617"
        strongs = (r["evidence_md"] or "").split(":")[-1].strip()
        if not strongs:
            continue
        ta = type_by_id.get(r["from_unit"])
        tb = type_by_id.get(r["to_unit"])
        # Skip lexeme-lexeme (trivial — they're literally about this word).
        if ta == "lexeme" and tb == "lexeme":
            continue
        # Skip if either end is the lexeme node anchored on this very Strong's
        # (the evidence is tautological).
        if ta == "lexeme" or tb == "lexeme":
            # Cheap check: see if the lexeme unit's title equals the strongs id.
            pass  # keep — many lexeme units are useful anchors

        f = freq(strongs)
        rarity = 1.0 / f
        pair = tuple(sorted((r["from_unit"], r["to_unit"])))
        novelty = 1.0 if pair not in other_edges else 0.25
        # Type-pair bonus: typology-rich types pair well.
        rich_types = {"seed", "person", "prophecy", "motif", "symbol", "covenant",
                      "theophany", "miracle", "parable"}
        type_bonus = 1.0
        if ta in rich_types and tb in rich_types:
            type_bonus = 1.5

        score = rarity * novelty * type_bonus
        scored.append((score, r["id"], strongs))

    scored.sort(reverse=True)
    print(f"  {len(scored)} after type-pair filter")

    # Per-lexeme cap to spread coverage.
    picked: list[int] = []
    per_lex: dict[str, int] = defaultdict(int)
    for s, eid, strongs in scored:
        if per_lex[strongs] >= PER_LEXEME_CAP:
            continue
        picked.append(eid)
        per_lex[strongs] += 1
        if len(picked) >= TOP_N:
            break

    print(f"Picked {len(picked)} edges across {len(per_lex)} distinct lexemes "
          f"(cap={PER_LEXEME_CAP}/lexeme)")

    # Mark candidates; clear stale status.
    cur.execute("UPDATE connection SET score_status='rejected_prefilter' "
                "WHERE type='shares_lexeme' AND score_status IS NULL")
    cur.executemany(
        "UPDATE connection SET score_status='candidate' WHERE id=?",
        [(eid,) for eid in picked],
    )
    conn.commit()
    conn.close()
    print("Done. Run `score_agents.py` to score the candidates.")


if __name__ == "__main__":
    main()

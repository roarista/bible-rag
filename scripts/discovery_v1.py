"""Discovery Engine V1 — surface candidate echoes between units that don't yet
have a typed edge between them.

For each unit, look at its k semantic neighbors. Any neighbor with which the
unit shares NO existing edge is a candidate echo. Combine features:
  - cosine similarity (from sqlite-vec)
  - shared rare lexemes (count + min rarity)
  - sefaria_link between their refs (if any)
  - canonical-OT/NT direction bonus (OT seed → NT seed has higher typological prior)

Output: writes top-N candidates to the `connection` table with
type='discovered_echo', score_status='candidate' (so the same scoring pipeline
can be applied afterwards).
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

K_NEIGHBORS = 25
TOP_N = 1000


def main() -> None:
    conn = connect()
    cur = conn.cursor()

    # Map: unit_id → set of unit_ids it already shares any edge with.
    print("Indexing existing edges…")
    has_edge: dict[int, set[int]] = defaultdict(set)
    for r in cur.execute("SELECT from_unit, to_unit FROM connection"):
        a, b = r["from_unit"], r["to_unit"]
        has_edge[a].add(b)
        has_edge[b].add(a)
    print(f"  {sum(len(v) for v in has_edge.values()) // 2} unordered pairs already connected")

    # Get all units with embeddings.
    units = cur.execute(
        "SELECT u.id, u.slug, u.type, u.title, u.frontmatter "
        "FROM unit u "
        "JOIN embedding_meta m ON m.unit_id=u.id"
    ).fetchall()
    unit_by_id = {u["id"]: u for u in units}
    print(f"  {len(units)} units with embeddings")

    # Shared-rare-lexeme cache from existing shares_lexeme edges (already encodes the work).
    # Pair → list[strongs]
    shared_lex: dict[tuple[int, int], list[str]] = defaultdict(list)
    for r in cur.execute(
        "SELECT from_unit, to_unit, evidence_md FROM connection "
        "WHERE type='shares_lexeme'"
    ):
        key = tuple(sorted((r["from_unit"], r["to_unit"])))
        s = (r["evidence_md"] or "").split(":")[-1].strip()
        if s:
            shared_lex[key].append(s)

    # Sefaria-link pair cache (any sefaria_* edge between two unit IDs).
    sefaria_pair: set[tuple[int, int]] = set()
    for r in cur.execute(
        "SELECT from_unit, to_unit FROM connection WHERE type LIKE 'sefaria_%'"
    ):
        sefaria_pair.add(tuple(sorted((r["from_unit"], r["to_unit"]))))

    # Walk semantic neighbors via sqlite-vec.
    candidates: dict[tuple[int, int], dict] = {}
    print(f"Querying {K_NEIGHBORS} semantic neighbors per unit…")
    for idx, u in enumerate(units):
        rows = cur.execute(
            """
            SELECT m.unit_id AS uid, vec.distance
            FROM embedding_vec vec
            JOIN embedding_meta m ON m.id = vec.embedding_id
            WHERE vec.vector MATCH (
                SELECT v2.vector FROM embedding_vec v2
                JOIN embedding_meta m2 ON m2.id=v2.embedding_id
                WHERE m2.unit_id=?
            )
            AND vec.k = ?
            ORDER BY vec.distance
            """,
            (u["id"], K_NEIGHBORS + 1),
        ).fetchall()
        for nb in rows:
            other = nb["uid"]
            if other == u["id"]:
                continue
            if other in has_edge[u["id"]]:
                continue
            pair = tuple(sorted((u["id"], other)))
            if pair in candidates:
                continue
            sim = 1.0 - nb["distance"]  # cosine sim approximation
            candidates[pair] = {
                "sim": sim,
                "shared_lex": shared_lex.get(pair, []),
                "sefaria": pair in sefaria_pair,
            }
        if (idx + 1) % 100 == 0:
            print(f"  processed {idx + 1}/{len(units)}")

    print(f"  {len(candidates)} candidate pairs (no existing edge)")

    # Type-pair bonus: cross-testament + rich types.
    rich_types = {"seed", "person", "prophecy", "motif", "symbol", "covenant",
                  "theophany", "miracle", "parable", "festival"}

    def composite_score(pair: tuple[int, int], feats: dict) -> float:
        u1, u2 = unit_by_id[pair[0]], unit_by_id[pair[1]]
        s = feats["sim"]
        # Lexeme boost: scaled by count, capped.
        s += 0.05 * min(len(feats["shared_lex"]), 4)
        # Sefaria boost.
        if feats["sefaria"]:
            s += 0.10
        # Type-pair richness.
        if u1["type"] in rich_types and u2["type"] in rich_types:
            s += 0.05
        # Slight cross-testament bonus when refs span OT and NT — use
        # frontmatter ot_refs vs nt_refs presence.
        def has_refs(u, key):
            try:
                fm = json.loads(u["frontmatter"]) if u["frontmatter"] else {}
                return bool(fm.get(key))
            except json.JSONDecodeError:
                return False
        if (has_refs(u1, "ot_refs") and has_refs(u2, "nt_refs")) or \
           (has_refs(u1, "nt_refs") and has_refs(u2, "ot_refs")):
            s += 0.08
        return min(s, 1.0)

    ranked = sorted(candidates.items(), key=lambda kv: composite_score(*kv), reverse=True)
    top = ranked[:TOP_N]
    print(f"  Top {len(top)} candidates")

    # Persist top candidates as discovered_echo edges with score_status='candidate'.
    # Always emit as (lower_id → higher_id) for determinism.
    inserted = 0
    for pair, feats in top:
        a, b = pair
        composite = composite_score(pair, feats)
        evidence = (
            f"sim={feats['sim']:.3f} "
            f"shared_lex={len(feats['shared_lex'])} "
            f"sefaria={'y' if feats['sefaria'] else 'n'}"
        )
        cur.execute(
            """
            INSERT OR IGNORE INTO connection
                (from_unit, to_unit, type, confidence, source, evidence_md,
                 score_status, score)
            VALUES (?, ?, 'discovered_echo', ?, 'discovery-v1', ?, 'candidate', ?)
            """,
            (a, b, composite, evidence, composite),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    print(f"\nInserted {inserted} discovered_echo candidates (composite score is the prior).")

    # Quick top-15 preview
    print("\nTop 15 discovered candidates (no prior edge between units):")
    top_rows = cur.execute(
        "SELECT c.score, u1.title AS a, u1.type AS ta, u2.title AS b, u2.type AS tb, c.evidence_md "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='discovered_echo' "
        "ORDER BY c.score DESC LIMIT 15"
    ).fetchall()
    for r in top_rows:
        print(f"  {r['score']:.3f}  {r['ta']:9s} {r['a']} ↔ {r['tb']:9s} {r['b']}   [{r['evidence_md']}]")
    conn.close()


if __name__ == "__main__":
    main()

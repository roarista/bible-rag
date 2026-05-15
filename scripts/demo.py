"""Demonstrate the queries the system can already answer.

Runs against the SQLite database built by scripts/build.py. Shows:
  • the hubs (most-connected units)
  • who shares a symbol with whom
  • full-text search
  • semantic similarity (only if embeddings exist)
"""

from bible_rag.db import connect
from bible_rag import query as Q


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    conn = connect()

    section("THE HUBS — most-connected nodes in the graph")
    for r in Q.hubs(conn, top_n=10):
        print(f"  [{r['type']:<6}] {r['title']:<35} degree={r['degree']}")

    section("ALL SEEDS THAT USE THE SYMBOL 'Lamb'")
    for r in Q.seeds_sharing_symbol(conn, "symbol:Lamb"):
        print(f"  • {r['title']}  (slug={r['slug']})")

    section("ALL CONNECTIONS OUTGOING FROM 'Abraham-Isaac'")
    for r in Q.neighbors(conn, "seed:Abraham-Isaac"):
        print(f"  --[{r['edge_type']:<14}]--> {r['title']:<30} ({r['type']})")

    section("FULL-TEXT SEARCH: 'pierced'")
    for r in Q.fts(conn, "pierced", limit=8):
        print(f"  [{r['type']:<6}] {r['title']}")
        print(f"           {r['snippet']}")

    section("FULL-TEXT SEARCH: 'three days resurrection'")
    for r in Q.fts(conn, "three days resurrection", limit=8):
        print(f"  [{r['type']:<6}] {r['title']}")
        print(f"           {r['snippet']}")

    section("SEMANTIC SIMILARITY: units most like 'Abraham-Isaac'")
    try:
        for r in Q.similar_to_unit(conn, "seed:Abraham-Isaac", k=5):
            print(f"  distance={r['distance']:.4f}  [{r['type']:<6}] {r['title']}")
    except ValueError as e:
        print(f"  (no embeddings yet — run `python scripts/build.py --embed`)")
    except Exception as e:
        print(f"  ERROR: {e}")

    section("SEMANTIC SEARCH: ad-hoc text → nearest units")
    try:
        for r in Q.similar_to_text(
            conn,
            "A father offers his beloved only son on a mountain as a sacrifice",
            k=5,
        ):
            print(f"  distance={r['distance']:.4f}  [{r['type']:<6}] {r['title']}")
    except RuntimeError as e:
        print(f"  (skipped — {e})")
    except Exception as e:
        print(f"  ERROR: {e}")

    conn.close()


if __name__ == "__main__":
    main()

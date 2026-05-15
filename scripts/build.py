"""One-shot build: init schema → import seeds → (optionally) embed.

Usage:
    uv run python scripts/build.py            # init + import (no embeddings)
    uv run python scripts/build.py --embed    # also embed (requires OPENAI_API_KEY)
"""

import sys
from bible_rag import DB_PATH
from bible_rag.db import init
from bible_rag.importer import import_all


def main(argv: list[str]) -> int:
    do_embed = "--embed" in argv

    print(f"Initializing DB at {DB_PATH} …")
    conn = init()

    print("Importing seeds / symbols / motifs from vault …")
    result = import_all(conn)
    print(f"  units imported: {result['units']}")
    for t, n in result["by_type"].items():
        print(f"    • {t}: {n}")
    print(f"  connections (typed edges): {result['connections']}")

    if do_embed:
        from bible_rag.embedder import embed_units
        print("\nEmbedding units with OpenAI text-embedding-3-large …")
        try:
            r = embed_units(conn)
            print(f"  {r}")
        except RuntimeError as e:
            print(f"  SKIPPED: {e}")
            return 1
    else:
        print("\n(skipping embeddings; pass --embed to generate them)")

    conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

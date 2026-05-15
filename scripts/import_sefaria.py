"""Import Sefaria's intertextual links into ``sefaria_link`` table.

Sefaria publishes (CC-BY 4.0) a complete export of their corpus at
``gs://sefaria-export/`` and a mirror over HTTPS at
``https://storage.googleapis.com/sefaria-export/``. Inside that bucket the
``links/`` directory contains ~13 CSV shards (~530 MB total) of typed
intertextual connections — millions of edges between Tanakh, Talmud, Mishnah,
Midrash, commentaries, halakhic codes, and modern works.

CSV columns are::

    Citation 1, Citation 2, Conection Type, Text 1, Text 2, Category 1, Category 2

Where:
- "Citation N" is a Sefaria-format ref (e.g. ``Genesis 1:1``,
  ``Genesis 1:1-6:8``, ``Rashi on Genesis 1:1:1``, ``Sanhedrin 74b:9``).
- "Conection Type" (sic) is one of: commentary, quotation, midrash,
  reference, mishneh-torah, summary, related, allusion, targum, ... etc.
  Some rows have an empty type.
- "Category N" is Sefaria's top-level category for the text
  (Tanakh, Mishnah, Talmud, Midrash, Halakhah, Liturgy, Reference, ...).

This script:
    1. Downloads each ``links{N}.csv`` shard into ``data/sefaria/`` (idempotent).
    2. Creates ``sefaria_link`` (+ indexes) if not present.
    3. Streams each CSV, parses citations into (book, chapter, verse) when
       possible, and INSERT OR IGNORE on a UNIQUE constraint.
    4. Reports totals, link-type breakdown, and biblical↔biblical counts.

Re-running is safe — UNIQUE(source_ref, target_ref, link_type) +
INSERT OR IGNORE keep it idempotent. Existing tables are untouched.

Usage::

    cd ~/code/bible-rag
    uv run python scripts/import_sefaria.py

License of the data: CC-BY 4.0 (Sefaria).
"""

from __future__ import annotations

import csv
import re
import sys
import urllib.request
from pathlib import Path
from typing import Iterator

from bible_rag import PROJECT_ROOT
from bible_rag.db import connect


BUCKET_BASE = "https://storage.googleapis.com/sefaria-export/links"
NUM_SHARDS = 13  # links0.csv … links12.csv
DATA_DIR = PROJECT_ROOT / "data" / "sefaria"

# Books considered "biblical canon" for the purposes of tagging
# biblical↔biblical typology links. We accept the Tanakh (Hebrew Bible) books
# under their Sefaria English names. Sefaria does not host the Christian NT,
# so this is OT-only. Christian deuterocanonical books (Tobit, Judith, etc.)
# are present in Sefaria but excluded here to keep the canon definition tight.
BIBLICAL_BOOKS: set[str] = {
    # Torah
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    # Nevi'im (Prophets)
    "Joshua", "Judges", "I Samuel", "II Samuel", "I Kings", "II Kings",
    "Isaiah", "Jeremiah", "Ezekiel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    # Ketuvim (Writings)
    "Psalms", "Proverbs", "Job",
    "Song of Songs", "Ruth", "Lamentations", "Ecclesiastes", "Esther",
    "Daniel", "Ezra", "Nehemiah", "I Chronicles", "II Chronicles",
}

# Sefaria uses "Song of Songs" but sometimes "Shir HaShirim"; we accept both.
BIBLICAL_BOOK_ALIASES = {
    "Shir HaShirim": "Song of Songs",
    "Kohelet": "Ecclesiastes",
    "Eikhah": "Lamentations",
}

# Sefaria book-name prefix: optionally "I"/"II"/"III", then one or more
# capitalized words (allowing apostrophe). We anchor at the start of the ref
# and stop at the first space-then-digit (which begins the chapter).
# This captures "Genesis", "I Samuel", "Song of Songs", etc.
# We DO NOT match prefixes like "Mishnah ...", "Rashi on ...", "Sanhedrin"
# (only chapters, no colon), etc. — those won't appear in BIBLICAL_BOOKS so
# the biblical-to-biblical flag remains correct even if we parse them.
_REF_BOOK_RE = re.compile(
    r"^((?:I{1,3}\s+)?[A-Z][a-zA-Z']*(?:\s+(?:of\s+)?[A-Z][a-zA-Z']*)*)"
    r"\s+(\d+)(?::(\d+))?"
)


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _shard_path(i: int) -> Path:
    return DATA_DIR / f"links{i}.csv"


def _download_shards() -> list[Path]:
    """Download all link CSV shards (idempotent)."""
    _ensure_data_dir()
    paths: list[Path] = []
    for i in range(NUM_SHARDS):
        dest = _shard_path(i)
        url = f"{BUCKET_BASE}/links{i}.csv"
        if dest.exists() and dest.stat().st_size > 0:
            print(f"  shard {i}: present ({dest.stat().st_size:,} bytes)")
        else:
            print(f"  shard {i}: downloading {url}")
            req = urllib.request.Request(
                url, headers={"User-Agent": "bible-rag/sefaria-importer"}
            )
            with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
                # stream in chunks
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
            print(f"    -> {dest.stat().st_size:,} bytes")
        paths.append(dest)
    return paths


def _parse_ref(ref: str) -> tuple[str, int, int] | None:
    """Parse a Sefaria-style ref into (book, chapter, verse) when possible.

    Returns None for refs that aren't a clean Book Chap:Verse pattern
    (e.g. ``Rashi on Genesis 1:1:1``, ``Sanhedrin 74b:9``, ``Mishnah ...``).
    """
    s = ref.strip()
    m = _REF_BOOK_RE.match(s)
    if not m:
        return None
    book = m.group(1).strip()
    book = BIBLICAL_BOOK_ALIASES.get(book, book)
    try:
        ch = int(m.group(2))
        v = int(m.group(3)) if m.group(3) is not None else 0
    except ValueError:
        return None
    return book, ch, v


def _is_biblical(parsed: tuple[str, int, int] | None) -> bool:
    return parsed is not None and parsed[0] in BIBLICAL_BOOKS


def ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sefaria_link (
            id INTEGER PRIMARY KEY,
            source_ref TEXT NOT NULL,
            source_book TEXT,
            source_chapter INTEGER,
            source_verse INTEGER,
            target_ref TEXT NOT NULL,
            target_book TEXT,
            target_chapter INTEGER,
            target_verse INTEGER,
            link_type TEXT,
            source_category TEXT,
            target_category TEXT,
            biblical_to_biblical INTEGER NOT NULL DEFAULT 0,
            source_path TEXT,
            UNIQUE(source_ref, target_ref, link_type)
        );
        CREATE INDEX IF NOT EXISTS idx_sefaria_link_src
            ON sefaria_link(source_book, source_chapter, source_verse);
        CREATE INDEX IF NOT EXISTS idx_sefaria_link_tgt
            ON sefaria_link(target_book, target_chapter, target_verse);
        CREATE INDEX IF NOT EXISTS idx_sefaria_link_type
            ON sefaria_link(link_type);
        CREATE INDEX IF NOT EXISTS idx_sefaria_link_bib
            ON sefaria_link(biblical_to_biblical);
        """
    )
    conn.commit()


def _iter_rows(csv_path: Path) -> Iterator[tuple]:
    """Yield rows ready for INSERT into sefaria_link."""
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return
        for row in reader:
            if len(row) < 7:
                # malformed
                continue
            src_ref, tgt_ref, link_type, _t1, _t2, cat1, cat2 = row[:7]
            src_ref = (src_ref or "").strip()
            tgt_ref = (tgt_ref or "").strip()
            if not src_ref or not tgt_ref:
                continue
            link_type = (link_type or "").strip().lower() or None
            src_p = _parse_ref(src_ref)
            tgt_p = _parse_ref(tgt_ref)
            bib = 1 if (_is_biblical(src_p) and _is_biblical(tgt_p)) else 0
            yield (
                src_ref,
                src_p[0] if src_p else None,
                src_p[1] if src_p else None,
                src_p[2] if src_p else None,
                tgt_ref,
                tgt_p[0] if tgt_p else None,
                tgt_p[1] if tgt_p else None,
                tgt_p[2] if tgt_p else None,
                link_type,
                (cat1 or "").strip() or None,
                (cat2 or "").strip() or None,
                bib,
                csv_path.name,
            )


INSERT_SQL = (
    "INSERT OR IGNORE INTO sefaria_link "
    "(source_ref, source_book, source_chapter, source_verse, "
    " target_ref, target_book, target_chapter, target_verse, "
    " link_type, source_category, target_category, "
    " biblical_to_biblical, source_path) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def import_shard(conn, csv_path: Path, batch_size: int = 5000) -> tuple[int, int]:
    """Import one CSV shard. Returns (rows_seen, rows_inserted)."""
    before = conn.execute("SELECT COUNT(*) FROM sefaria_link").fetchone()[0]
    batch: list[tuple] = []
    seen = 0
    for row in _iter_rows(csv_path):
        batch.append(row)
        seen += 1
        if len(batch) >= batch_size:
            conn.executemany(INSERT_SQL, batch)
            batch.clear()
    if batch:
        conn.executemany(INSERT_SQL, batch)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM sefaria_link").fetchone()[0]
    return seen, after - before


def report(conn) -> None:
    total = conn.execute("SELECT COUNT(*) FROM sefaria_link").fetchone()[0]
    print(f"\nTotal rows in sefaria_link: {total:,}")

    print("\nTop 10 link_types by count:")
    rows = conn.execute(
        "SELECT COALESCE(link_type, '<null>') AS t, COUNT(*) AS n "
        "FROM sefaria_link GROUP BY t ORDER BY n DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        print(f"  {r['t']:<24} {r['n']:>12,}")

    bib = conn.execute(
        "SELECT COUNT(*) FROM sefaria_link WHERE biblical_to_biblical = 1"
    ).fetchone()[0]
    print(f"\nBiblical↔Biblical links: {bib:,}")

    print("\n5 sample rows:")
    samples = conn.execute(
        "SELECT source_ref, target_ref, link_type, biblical_to_biblical "
        "FROM sefaria_link ORDER BY id LIMIT 5"
    ).fetchall()
    for r in samples:
        print(f"  [{r['link_type']}] {r['source_ref']} -> {r['target_ref']} "
              f"(bib={r['biblical_to_biblical']})")

    print("\n5 sample biblical↔biblical rows:")
    samples = conn.execute(
        "SELECT source_ref, target_ref, link_type FROM sefaria_link "
        "WHERE biblical_to_biblical = 1 ORDER BY RANDOM() LIMIT 5"
    ).fetchall()
    for r in samples:
        print(f"  [{r['link_type']}] {r['source_ref']} -> {r['target_ref']}")


def main(argv: list[str]) -> int:
    print("Downloading Sefaria link CSV shards if needed …")
    shards = _download_shards()

    print("\nOpening DB and ensuring schema …")
    conn = connect()
    try:
        ensure_schema(conn)
        total_seen = 0
        total_inserted = 0
        for i, path in enumerate(shards):
            print(f"\nImporting shard {i} ({path.name}) …")
            seen, inserted = import_shard(conn, path)
            total_seen += seen
            total_inserted += inserted
            print(f"  seen={seen:,}  inserted={inserted:,}")
        print(f"\nTotals: seen={total_seen:,}  inserted={total_inserted:,}")
        report(conn)
    finally:
        conn.close()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

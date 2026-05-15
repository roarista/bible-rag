"""Import the Treasury of Scripture Knowledge (TSK) cross-references.

The TSK is a public-domain compilation of ~500,000 Bible verse cross-references.
OpenBible.info distributes a curated, vote-weighted version as a CSV
(typical fields: ``From Verse,To Verse,Votes`` with USFM-style refs like
``Gen.1.1``).

This script:
    1. Downloads the cross-references zip into ``~/code/bible-rag/data/tsk/``
       (idempotent — skips if already present) and extracts the CSV.
    2. Parses each row into (book, chapter, verse) tuples for both endpoints.
    3. Creates a ``verse_cross_ref`` table (+ index) in the project DB
       if it does not already exist.
    4. Bulk-inserts the parsed rows with ``ON CONFLICT DO NOTHING`` so the
       import is idempotent.
    5. Reports the final row count.

Usage::

    cd ~/code/bible-rag
    uv run python scripts/import_tsk.py

The script does NOT run automatically — the user must invoke it explicitly.
Embedding is unaffected (this is verse-level cross-reference data, not units).

Source URL (OpenBible.info Labs, public domain):
    https://a.openbible.info/data/cross-references.zip

If the URL changes, see https://www.openbible.info/labs/cross-references/
for the current location.
"""

from __future__ import annotations

import csv
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Iterator

from bible_rag import PROJECT_ROOT
from bible_rag.db import connect


TSK_URL = "https://a.openbible.info/data/cross-references.zip"
DATA_DIR = PROJECT_ROOT / "data" / "tsk"
ZIP_PATH = DATA_DIR / "cross-references.zip"

# OpenBible's CSV occasionally uses tabs rather than commas; we try both.
_SEP_CANDIDATES = ("\t", ",")

# USFM-style verse refs: "Gen.1.1" or with a range "Gen.1.1-Gen.1.3"
# We only take the *first* verse of any range for the From side, and the
# *first* verse on the To side; the range tail is preserved as a sibling row
# only if the importer is extended later.
_REF_RE = re.compile(r"^([1-3]?[A-Za-z]+)\.(\d+)\.(\d+)")


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _download_zip(url: str = TSK_URL, dest: Path = ZIP_PATH) -> Path:
    """Download the TSK zip if it isn't already on disk."""
    _ensure_data_dir()
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  zip already present: {dest} ({dest.stat().st_size:,} bytes)")
        return dest
    print(f"  downloading {url} -> {dest}")
    req = urllib.request.Request(url, headers={"User-Agent": "bible-rag/tsk-importer"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as out:
        out.write(resp.read())
    print(f"  downloaded {dest.stat().st_size:,} bytes")
    return dest


def _open_csv(zip_path: Path) -> tuple[io.TextIOWrapper, str]:
    """Open the first .txt/.csv file inside the zip as a text stream."""
    zf = zipfile.ZipFile(zip_path)
    members = [n for n in zf.namelist() if n.lower().endswith((".txt", ".csv"))]
    if not members:
        raise RuntimeError(f"No .txt/.csv member found in {zip_path}")
    name = members[0]
    raw = zf.open(name)
    return io.TextIOWrapper(raw, encoding="utf-8", newline=""), name


def _detect_separator(sample: str) -> str:
    counts = {sep: sample.count(sep) for sep in _SEP_CANDIDATES}
    return max(counts, key=counts.get)


def _parse_ref(ref: str) -> tuple[str, int, int] | None:
    """Parse a USFM-style ref like ``Gen.1.1`` (ignores any trailing range)."""
    m = _REF_RE.match(ref.strip())
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3))


def _iter_rows(stream: io.TextIOWrapper) -> Iterator[tuple]:
    """Yield (from_book, from_ch, from_v, to_book, to_ch, to_v, votes) tuples."""
    sample = stream.read(4096)
    sep = _detect_separator(sample)
    stream.seek(0)
    reader = csv.reader(stream, delimiter=sep)

    header = next(reader, None)
    if header is None:
        return
    # If the first row doesn't look like a header (no letters in any field),
    # treat it as data by yielding it first.
    looks_like_header = any(any(c.isalpha() for c in cell) and "." not in cell
                            for cell in header)
    rows: Iterable[list[str]] = reader if looks_like_header else _chain_once(header, reader)

    for row in rows:
        if not row or len(row) < 2:
            continue
        f = _parse_ref(row[0])
        t = _parse_ref(row[1])
        if not f or not t:
            continue
        try:
            votes = int(row[2]) if len(row) > 2 and row[2].strip() else 0
        except ValueError:
            votes = 0
        yield (*f, *t, votes)


def _chain_once(first: list[str], rest: Iterable[list[str]]) -> Iterator[list[str]]:
    yield first
    for r in rest:
        yield r


def ensure_schema(conn) -> None:
    """Create the verse_cross_ref table + index if not present."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS verse_cross_ref (
            id INTEGER PRIMARY KEY,
            from_book TEXT NOT NULL,
            from_chapter INTEGER NOT NULL,
            from_verse INTEGER NOT NULL,
            to_book TEXT NOT NULL,
            to_chapter INTEGER NOT NULL,
            to_verse INTEGER NOT NULL,
            votes INTEGER NOT NULL DEFAULT 0,
            source TEXT,
            UNIQUE(from_book, from_chapter, from_verse,
                   to_book, to_chapter, to_verse)
        );
        CREATE INDEX IF NOT EXISTS idx_xref_from
            ON verse_cross_ref(from_book, from_chapter, from_verse);
        CREATE INDEX IF NOT EXISTS idx_xref_to
            ON verse_cross_ref(to_book, to_chapter, to_verse);
        """
    )
    conn.commit()


def import_tsk(
    conn,
    *,
    zip_path: Path = ZIP_PATH,
    source_label: str = "tsk-openbible",
    batch_size: int = 5000,
) -> int:
    """Import TSK cross-references into ``verse_cross_ref``. Returns rows inserted."""
    ensure_schema(conn)

    stream, member_name = _open_csv(zip_path)
    print(f"  reading {member_name} from zip")

    insert_sql = (
        "INSERT INTO verse_cross_ref "
        "(from_book, from_chapter, from_verse, "
        " to_book, to_chapter, to_verse, votes, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(from_book, from_chapter, from_verse, "
        "             to_book, to_chapter, to_verse) DO NOTHING"
    )

    before = conn.execute("SELECT COUNT(*) FROM verse_cross_ref").fetchone()[0]

    batch: list[tuple] = []
    total_seen = 0
    for row in _iter_rows(stream):
        batch.append((*row, source_label))
        total_seen += 1
        if len(batch) >= batch_size:
            conn.executemany(insert_sql, batch)
            batch.clear()
    if batch:
        conn.executemany(insert_sql, batch)
    conn.commit()
    stream.close()

    after = conn.execute("SELECT COUNT(*) FROM verse_cross_ref").fetchone()[0]
    inserted = after - before
    print(f"  rows parsed: {total_seen:,}")
    print(f"  rows inserted (new): {inserted:,}")
    print(f"  total in table: {after:,}")
    return inserted


def main(argv: list[str]) -> int:
    print("Downloading TSK cross-references zip if needed …")
    _download_zip()

    print("Opening DB and ensuring schema …")
    conn = connect()
    try:
        print("Importing TSK rows …")
        import_tsk(conn)
    finally:
        conn.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

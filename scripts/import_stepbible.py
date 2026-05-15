"""Ingest STEPBible (Tyndale House) lexicons into the Bible-RAG SQLite DB.

Sources (CC BY 4.0):
    - TBESH: Translators' Brief lexicon of Extended Strongs for Hebrew
    - TBESG: Translators' Brief lexicon of Extended Strongs for Greek

These are dictionary-style lexicon entries keyed by Extended Strong's number.
They complement MACULA (per-token treebanks) and the existing tiny `lexeme`
unit table. They are stored in dedicated tables to avoid any conflict.

Note: STEPBible-Data does NOT contain a Tyndale-vetted TSK (TVTSK) file as of
this writing. The original OpenBible TSK is already loaded into
`verse_cross_ref`. The schema for `stepbible_xref` is still created so future
TVTSK data can be ingested cleanly, but no rows are inserted today.

Run:
    uv run python scripts/import_stepbible.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sqlite3
from pathlib import Path

REPO_URL = "https://github.com/STEPBible/STEPBible-Data.git"
CLONE_DIR = Path("/tmp/STEPBible-Data")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bible_rag.db"

TBESH_PATH = (
    CLONE_DIR
    / "Lexicons"
    / "TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt"
)
TBESG_PATH = (
    CLONE_DIR
    / "Lexicons"
    / "TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS stepbible_lex_hebrew (
    id INTEGER PRIMARY KEY,
    strongs TEXT,
    dstrongs TEXT,
    ustrongs TEXT,
    lemma TEXT,
    transliteration TEXT,
    morph TEXT,
    gloss TEXT,
    extended_gloss TEXT,
    senses TEXT,
    UNIQUE(strongs)
);

CREATE TABLE IF NOT EXISTS stepbible_lex_greek (
    id INTEGER PRIMARY KEY,
    strongs TEXT,
    dstrongs TEXT,
    ustrongs TEXT,
    lemma TEXT,
    transliteration TEXT,
    morph TEXT,
    gloss TEXT,
    extended_gloss TEXT,
    senses TEXT,
    UNIQUE(strongs)
);

CREATE TABLE IF NOT EXISTS stepbible_xref (
    id INTEGER PRIMARY KEY,
    from_ref TEXT NOT NULL,
    from_book TEXT, from_chapter INTEGER, from_verse INTEGER,
    to_ref TEXT NOT NULL,
    to_book TEXT, to_chapter INTEGER, to_verse INTEGER,
    rationale TEXT,
    UNIQUE(from_ref, to_ref)
);
"""


def ensure_clone() -> None:
    if CLONE_DIR.exists() and (CLONE_DIR / "Lexicons").exists():
        print(f"[clone] reusing {CLONE_DIR}")
        return
    print(f"[clone] cloning {REPO_URL} -> {CLONE_DIR}")
    if CLONE_DIR.exists():
        subprocess.run(["rm", "-rf", str(CLONE_DIR)], check=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(CLONE_DIR)],
        check=True,
    )


# The data section in TBESH/TBESG starts with an 8-col header row whose first
# cell is "eStrong#" (Hebrew) or "EStrong#" (Greek). Entry rows begin with the
# strongs token (e.g. "H0001" or "G0001"). We split on TAB and keep rows whose
# first cell matches that pattern.
STRONGS_RE = re.compile(r"^[HG]\d{1,5}[A-Za-z]?$")


def parse_lexicon(path: Path) -> list[tuple]:
    rows: list[tuple] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line or "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) < 8:
                continue
            estrongs = parts[0].strip()
            if not STRONGS_RE.match(estrongs):
                continue
            dstrongs_raw = parts[1].strip()
            ustrongs = parts[2].strip().rstrip(",").strip()
            lemma = parts[3].strip()
            translit = parts[4].strip()
            morph = parts[5].strip()
            gloss = parts[6].strip()
            meaning = parts[7].strip()
            # dstrongs cell looks like "H0001G = a Part of" -> take token before " "
            dstrongs = dstrongs_raw.split()[0] if dstrongs_raw else ""
            # senses: split meaning on "<br>" newlines for a structured view
            senses = " | ".join(
                s.strip() for s in re.split(r"<br\s*/?>", meaning, flags=re.IGNORECASE) if s.strip()
            )
            rows.append(
                (
                    estrongs,
                    dstrongs,
                    ustrongs,
                    lemma,
                    translit,
                    morph,
                    gloss,
                    meaning,
                    senses,
                )
            )
    return rows


def insert_lex(conn: sqlite3.Connection, table: str, rows: list[tuple]) -> int:
    cur = conn.cursor()
    before = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    cur.executemany(
        f"""INSERT OR IGNORE INTO {table}
            (strongs, dstrongs, ustrongs, lemma, transliteration, morph,
             gloss, extended_gloss, senses)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    after = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return after - before


def main() -> None:
    ensure_clone()
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    print(f"[parse] TBESH from {TBESH_PATH.name}")
    heb_rows = parse_lexicon(TBESH_PATH)
    print(f"[parse]   {len(heb_rows)} Hebrew rows parsed")

    print(f"[parse] TBESG from {TBESG_PATH.name}")
    grk_rows = parse_lexicon(TBESG_PATH)
    print(f"[parse]   {len(grk_rows)} Greek rows parsed")

    heb_added = insert_lex(conn, "stepbible_lex_hebrew", heb_rows)
    grk_added = insert_lex(conn, "stepbible_lex_greek", grk_rows)

    print(f"[insert] stepbible_lex_hebrew: +{heb_added} rows")
    print(f"[insert] stepbible_lex_greek:  +{grk_added} rows")
    print(
        "[insert] stepbible_xref: schema ready; "
        "no TVTSK data in STEPBible-Data repo (skipped)"
    )

    # Totals & samples
    cur = conn.cursor()
    h_total = cur.execute("SELECT COUNT(*) FROM stepbible_lex_hebrew").fetchone()[0]
    g_total = cur.execute("SELECT COUNT(*) FROM stepbible_lex_greek").fetchone()[0]
    x_total = cur.execute("SELECT COUNT(*) FROM stepbible_xref").fetchone()[0]
    print(f"\n[totals] hebrew={h_total}  greek={g_total}  xref={x_total}")

    print("\n[sample] First 5 Hebrew entries:")
    for r in cur.execute(
        "SELECT strongs, lemma, transliteration, morph, gloss FROM stepbible_lex_hebrew ORDER BY id LIMIT 5"
    ):
        print(" ", r)
    print("\n[sample] First 5 Greek entries:")
    for r in cur.execute(
        "SELECT strongs, lemma, transliteration, morph, gloss FROM stepbible_lex_greek ORDER BY id LIMIT 5"
    ):
        print(" ", r)

    conn.close()
    print("\n[done] STEPBible lexicon ingest complete.")


if __name__ == "__main__":
    main()

"""Import MACULA Hebrew (WLC) and Greek (Nestle1904) treebanks into bible_rag.db.

Sources:
- Hebrew: https://github.com/Clear-Bible/macula-hebrew  (WLC/lowfat/*.xml per chapter)
- Greek:  https://github.com/Clear-Bible/macula-greek   (Nestle1904/tsv/macula-greek-Nestle1904.tsv)

Both are CC-BY 4.0. Each <w> in Hebrew XML / row in Greek TSV is one token.

Creates two NEW tables only:
  - macula_hebrew_token
  - macula_greek_token

Idempotent: PRIMARY KEY is `ref` (Clear.Bible's natural unique identifier).
Uses INSERT OR REPLACE so reruns refresh rather than duplicate.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "bible_rag.db"

HEB_REPO = Path("/tmp/macula-hebrew")
GRK_REPO = Path("/tmp/macula-greek")
HEB_URL = "https://github.com/Clear-Bible/macula-hebrew.git"
GRK_URL = "https://github.com/Clear-Bible/macula-greek.git"

# Book name -> ordinal mapping for parsing ref strings like "GEN 1:1!1" / "MAT 1:1!1"
# We just keep book code as-is; chapter/verse/word_index parsed from the ref.
REF_RE = re.compile(r"^([A-Za-z0-9]+)\s+(\d+):(\d+)!(\d+)(.*)$")


def ensure_repos() -> None:
    if not (HEB_REPO / "WLC" / "lowfat").exists():
        print(f"[clone] {HEB_URL} -> {HEB_REPO}")
        subprocess.run(
            ["git", "clone", "--depth", "1", HEB_URL, str(HEB_REPO)], check=True
        )
    if not (GRK_REPO / "Nestle1904" / "tsv").exists():
        print(f"[clone] {GRK_URL} -> {GRK_REPO}")
        subprocess.run(
            ["git", "clone", "--depth", "1", GRK_URL, str(GRK_REPO)], check=True
        )


SCHEMA = """
CREATE TABLE IF NOT EXISTS macula_hebrew_token (
    ref TEXT PRIMARY KEY,            -- e.g., "GEN 1:1!1"
    xml_id TEXT,
    book TEXT,
    chapter INTEGER,
    verse INTEGER,
    word_index INTEGER,
    surface TEXT,                    -- unicode w/ vowel points + cantillation (as published)
    transliteration TEXT,
    lemma TEXT,
    strong_lemma TEXT,
    strongs TEXT,                    -- "H####" prefix added
    morph TEXT,
    pos TEXT,
    gloss TEXT,
    english TEXT,
    sense_id TEXT,                   -- sensenumber from SDBH
    lexdomain TEXT,
    coredomain TEXT,
    sdbh TEXT,
    greek_cognate TEXT,              -- LXX/cognate Greek attr if present
    greek_strong TEXT
);
CREATE INDEX IF NOT EXISTS idx_macula_heb_bcv ON macula_hebrew_token(book, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_macula_heb_lemma ON macula_hebrew_token(lemma);
CREATE INDEX IF NOT EXISTS idx_macula_heb_strongs ON macula_hebrew_token(strongs);

CREATE TABLE IF NOT EXISTS macula_greek_token (
    ref TEXT PRIMARY KEY,            -- e.g., "MAT 1:1!1"
    xml_id TEXT,
    book TEXT,
    chapter INTEGER,
    verse INTEGER,
    word_index INTEGER,
    surface TEXT,                    -- inflected form (with diacritics)
    normalized TEXT,
    lemma TEXT,
    strongs TEXT,                    -- "G####" prefix added
    morph TEXT,
    role TEXT,
    class TEXT,
    type TEXT,
    gloss TEXT,
    english TEXT,
    person TEXT,
    number TEXT,
    gender TEXT,
    grammar_case TEXT,
    tense TEXT,
    voice TEXT,
    mood TEXT,
    degree TEXT,
    domain TEXT,
    ln TEXT,
    frame TEXT,
    subjref TEXT,
    referent TEXT
);
CREATE INDEX IF NOT EXISTS idx_macula_grk_bcv ON macula_greek_token(book, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_macula_grk_lemma ON macula_greek_token(lemma);
CREATE INDEX IF NOT EXISTS idx_macula_grk_strongs ON macula_greek_token(strongs);
"""


def parse_ref(ref: str) -> tuple[str, int, int, int]:
    """Parse 'GEN 1:1!1' -> ('GEN', 1, 1, 1). Handles trailing suffixes like '!1(a)'."""
    m = REF_RE.match(ref.strip())
    if not m:
        return ("", 0, 0, 0)
    return m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))


def normalize_strongs(raw: str | None, lang: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw[0].upper() in ("H", "G"):
        return raw.upper()
    # numeric -> prefix
    return f"{lang}{raw}"


# ---------- Hebrew ----------

HEB_COLUMNS = [
    "ref", "xml_id", "book", "chapter", "verse", "word_index",
    "surface", "transliteration", "lemma", "strong_lemma", "strongs",
    "morph", "pos", "gloss", "english", "sense_id", "lexdomain",
    "coredomain", "sdbh", "greek_cognate", "greek_strong",
]

HEB_SQL = (
    f"INSERT OR REPLACE INTO macula_hebrew_token ({', '.join(HEB_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * len(HEB_COLUMNS))})"
)


def iter_hebrew_tokens():
    lowfat_dir = HEB_REPO / "WLC" / "lowfat"
    # Per-chapter XML files. Skip the wrapper macula-hebrew-lowfat.xml.
    files = sorted(
        p for p in lowfat_dir.glob("*-lowfat.xml")
        if p.name != "macula-hebrew-lowfat.xml"
    )
    for fp in files:
        try:
            tree = ET.parse(fp)
        except ET.ParseError as e:
            print(f"[heb] parse error {fp.name}: {e}", file=sys.stderr)
            continue
        root = tree.getroot()
        # All <w> word elements anywhere in the tree.
        for w in root.iter("w"):
            a = w.attrib
            ref = a.get("ref", "").strip()
            if not ref:
                continue
            book, chap, verse, widx = parse_ref(ref)
            surface = (w.text or "").strip() or a.get("unicode")
            yield (
                ref,
                a.get("{http://www.w3.org/XML/1998/namespace}id") or a.get("id"),
                book, chap, verse, widx,
                surface,
                a.get("transliteration"),
                a.get("lemma"),
                a.get("stronglemma"),
                normalize_strongs(a.get("strongnumberx") or a.get("strong"), "H"),
                a.get("morph"),
                a.get("pos"),
                a.get("gloss"),
                a.get("english"),
                a.get("sensenumber"),
                a.get("lexdomain"),
                a.get("coredomain"),
                a.get("sdbh"),
                a.get("greek"),
                a.get("greekstrong"),
            )


def import_hebrew(conn: sqlite3.Connection) -> int:
    print("[heb] importing MACULA Hebrew (WLC/lowfat)...")
    cur = conn.cursor()
    n = 0
    batch = []
    for row in iter_hebrew_tokens():
        batch.append(row)
        if len(batch) >= 5000:
            cur.executemany(HEB_SQL, batch)
            n += len(batch)
            batch.clear()
            if n % 50000 == 0:
                print(f"  [heb] {n:,} rows...")
    if batch:
        cur.executemany(HEB_SQL, batch)
        n += len(batch)
    conn.commit()
    print(f"[heb] inserted/replaced {n:,} tokens")
    return n


# ---------- Greek ----------

GRK_COLUMNS = [
    "ref", "xml_id", "book", "chapter", "verse", "word_index",
    "surface", "normalized", "lemma", "strongs", "morph",
    "role", "class", "type", "gloss", "english",
    "person", "number", "gender", "grammar_case",
    "tense", "voice", "mood", "degree",
    "domain", "ln", "frame", "subjref", "referent",
]

GRK_SQL = (
    f"INSERT OR REPLACE INTO macula_greek_token ({', '.join(GRK_COLUMNS)}) "
    f"VALUES ({', '.join(['?'] * len(GRK_COLUMNS))})"
)


def import_greek(conn: sqlite3.Connection) -> int:
    """Greek source: Nestle1904 TSV. Header matches the file's column order."""
    tsv = GRK_REPO / "Nestle1904" / "tsv" / "macula-greek-Nestle1904.tsv"
    print(f"[grk] importing MACULA Greek from {tsv.name}...")
    cur = conn.cursor()
    n = 0
    batch = []
    with tsv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            ref = (r.get("ref") or "").strip()
            if not ref:
                continue
            book, chap, verse, widx = parse_ref(ref)
            batch.append((
                ref,
                r.get("xml:id"),
                book, chap, verse, widx,
                r.get("text"),
                r.get("normalized"),
                r.get("lemma"),
                normalize_strongs(r.get("strong"), "G"),
                r.get("morph"),
                r.get("role"),
                r.get("class"),
                r.get("type"),
                r.get("gloss"),
                r.get("english"),
                r.get("person"),
                r.get("number"),
                r.get("gender"),
                r.get("case"),
                r.get("tense"),
                r.get("voice"),
                r.get("mood"),
                r.get("degree"),
                r.get("domain"),
                r.get("ln"),
                r.get("frame"),
                r.get("subjref"),
                r.get("referent"),
            ))
            if len(batch) >= 5000:
                cur.executemany(GRK_SQL, batch)
                n += len(batch)
                batch.clear()
                if n % 50000 == 0:
                    print(f"  [grk] {n:,} rows...")
    if batch:
        cur.executemany(GRK_SQL, batch)
        n += len(batch)
    conn.commit()
    print(f"[grk] inserted/replaced {n:,} tokens")
    return n


# ---------- Verification ----------

def report(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for table, lang in [("macula_hebrew_token", "Hebrew"), ("macula_greek_token", "Greek")]:
        total = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n=== {lang}: {total:,} tokens in {table} ===")
        print("Top 20 lemmata by frequency:")
        rows = cur.execute(
            f"SELECT lemma, COUNT(*) c FROM {table} "
            f"WHERE lemma IS NOT NULL AND lemma <> '' "
            f"GROUP BY lemma ORDER BY c DESC LIMIT 20"
        ).fetchall()
        for lemma, c in rows:
            print(f"  {c:>6}  {lemma}")
        print("Sample rows:")
        for r in cur.execute(
            f"SELECT ref, surface, lemma, strongs, morph, gloss "
            f"FROM {table} LIMIT 5"
        ):
            print(f"  {r}")


def main() -> None:
    ensure_repos()
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    import_hebrew(conn)
    import_greek(conn)
    report(conn)
    conn.close()
    print("\n[done] MACULA Hebrew + Greek ingest complete.")


if __name__ == "__main__":
    main()

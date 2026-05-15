"""Cross-link the raw ingest tables (Sefaria, MACULA, Theographic) to the unit graph.

Three phases:
  1. Sefaria → unit edges    (biblical_to_biblical sefaria_link rows mapped to units
                              whose ot_refs/nt_refs contain the endpoints).
  2. Theographic enrichment  (person units gain birth/death/lineage/place data; the
                              frontmatter JSON column is updated in place).
  3. Shared-lexeme edges     (units that share a rare Strong's lexeme — frequency
                              below a threshold — get a `shares_lexeme` edge).

Usage:
    uv run python scripts/cross_link.py            # run all three phases
    uv run python scripts/cross_link.py --phase 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402


# ---------------------------------------------------------------------------
# Reference parsing
# ---------------------------------------------------------------------------

# Canonical book name → list of accepted aliases. Sefaria uses "I Kings" /
# "I Samuel" with Roman numerals; our frontmatter uses "1 Kings" / "1 Samuel".
BOOK_ALIASES = {
    "Genesis": ["Genesis", "Gen"],
    "Exodus": ["Exodus", "Exod"],
    "Leviticus": ["Leviticus", "Lev"],
    "Numbers": ["Numbers", "Num"],
    "Deuteronomy": ["Deuteronomy", "Deut"],
    "Joshua": ["Joshua", "Josh"],
    "Judges": ["Judges", "Judg"],
    "Ruth": ["Ruth"],
    "I Samuel": ["1 Samuel", "I Samuel", "1Sam"],
    "II Samuel": ["2 Samuel", "II Samuel", "2Sam"],
    "I Kings": ["1 Kings", "I Kings", "1Kgs"],
    "II Kings": ["2 Kings", "II Kings", "2Kgs"],
    "I Chronicles": ["1 Chronicles", "I Chronicles", "1Chr"],
    "II Chronicles": ["2 Chronicles", "II Chronicles", "2Chr"],
    "Ezra": ["Ezra"],
    "Nehemiah": ["Nehemiah", "Neh"],
    "Esther": ["Esther"],
    "Job": ["Job"],
    "Psalms": ["Psalms", "Psalm", "Ps"],
    "Proverbs": ["Proverbs", "Prov"],
    "Ecclesiastes": ["Ecclesiastes", "Eccl"],
    "Song of Songs": ["Song of Songs", "Song of Solomon", "Canticles"],
    "Isaiah": ["Isaiah", "Isa"],
    "Jeremiah": ["Jeremiah", "Jer"],
    "Lamentations": ["Lamentations", "Lam"],
    "Ezekiel": ["Ezekiel", "Ezek"],
    "Daniel": ["Daniel", "Dan"],
    "Hosea": ["Hosea", "Hos"],
    "Joel": ["Joel"],
    "Amos": ["Amos"],
    "Obadiah": ["Obadiah", "Obad"],
    "Jonah": ["Jonah"],
    "Micah": ["Micah", "Mic"],
    "Nahum": ["Nahum", "Nah"],
    "Habakkuk": ["Habakkuk", "Hab"],
    "Zephaniah": ["Zephaniah", "Zeph"],
    "Haggai": ["Haggai", "Hag"],
    "Zechariah": ["Zechariah", "Zech"],
    "Malachi": ["Malachi", "Mal"],
    "Matthew": ["Matthew", "Matt"],
    "Mark": ["Mark"],
    "Luke": ["Luke"],
    "John": ["John"],
    "Acts": ["Acts"],
    "Romans": ["Romans", "Rom"],
    "I Corinthians": ["1 Corinthians", "I Corinthians", "1Cor"],
    "II Corinthians": ["2 Corinthians", "II Corinthians", "2Cor"],
    "Galatians": ["Galatians", "Gal"],
    "Ephesians": ["Ephesians", "Eph"],
    "Philippians": ["Philippians", "Phil"],
    "Colossians": ["Colossians", "Col"],
    "I Thessalonians": ["1 Thessalonians", "I Thessalonians", "1Thess"],
    "II Thessalonians": ["2 Thessalonians", "II Thessalonians", "2Thess"],
    "I Timothy": ["1 Timothy", "I Timothy", "1Tim"],
    "II Timothy": ["2 Timothy", "II Timothy", "2Tim"],
    "Titus": ["Titus"],
    "Philemon": ["Philemon"],
    "Hebrews": ["Hebrews", "Heb"],
    "James": ["James", "Jas"],
    "I Peter": ["1 Peter", "I Peter", "1Pet"],
    "II Peter": ["2 Peter", "II Peter", "2Pet"],
    "I John": ["1 John", "I John", "1Jn"],
    "II John": ["2 John", "II John", "2Jn"],
    "III John": ["3 John", "III John", "3Jn"],
    "Jude": ["Jude"],
    "Revelation": ["Revelation", "Rev"],
}

# Build reverse map: any alias → canonical Sefaria-style name.
ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in BOOK_ALIASES.items():
    for a in aliases:
        ALIAS_TO_CANONICAL[a.lower()] = canonical
    ALIAS_TO_CANONICAL[canonical.lower()] = canonical

REF_RE = re.compile(
    r"^\s*(?P<book>[1-3]?\s?[A-Za-z][A-Za-z\s]*?)\s+"
    r"(?P<chap>\d+)"
    r"(?::(?P<v1>\d+)(?:-(?P<v2>\d+))?)?\s*$"
)


def parse_ref(ref: str) -> tuple[str, int, int, int] | None:
    """Parse e.g. 'Genesis 22:1-19' → ('Genesis', 22, 1, 19).

    Returns canonical book name + chapter + v_start + v_end. When no verse range
    is given (chapter only), returns (book, chap, 1, 999).
    """
    m = REF_RE.match(ref.replace("–", "-").replace("—", "-"))
    if not m:
        return None
    raw_book = re.sub(r"\s+", " ", m.group("book").strip())
    canonical = ALIAS_TO_CANONICAL.get(raw_book.lower())
    if not canonical:
        return None
    chap = int(m.group("chap"))
    v1 = int(m.group("v1")) if m.group("v1") else 1
    v2 = int(m.group("v2")) if m.group("v2") else v1
    return (canonical, chap, v1, v2)


# ---------------------------------------------------------------------------
# Phase 1: Sefaria → unit edges
# ---------------------------------------------------------------------------

def phase1_sefaria_edges(conn) -> int:
    print("\n=== Phase 1: Sefaria → unit edges ===")
    cur = conn.cursor()

    # Build a verse → [unit_ids] index from all unit frontmatter refs.
    verse_to_units: dict[tuple[str, int, int], set[int]] = defaultdict(set)
    units = cur.execute("SELECT id, slug, frontmatter FROM unit").fetchall()
    skipped_refs: set[str] = set()
    indexed = 0
    for u in units:
        if not u["frontmatter"]:
            continue
        try:
            fm = json.loads(u["frontmatter"])
        except json.JSONDecodeError:
            continue
        for key in ("ot_refs", "nt_refs", "refs"):
            for ref in fm.get(key) or []:
                parsed = parse_ref(str(ref))
                if not parsed:
                    skipped_refs.add(str(ref))
                    continue
                book, chap, v1, v2 = parsed
                for v in range(v1, v2 + 1):
                    verse_to_units[(book, chap, v)].add(u["id"])
                indexed += 1
    print(f"  Indexed {indexed} refs across {len(units)} units → "
          f"{len(verse_to_units)} verse slots, {len(skipped_refs)} unparseable refs")

    # Walk biblical_to_biblical Sefaria links and emit unit edges where both endpoints land in units.
    rows = cur.execute("""
        SELECT source_book, source_chapter, source_verse,
               target_book, target_chapter, target_verse,
               link_type
        FROM sefaria_link
        WHERE biblical_to_biblical=1
    """).fetchall()

    inserted = 0
    seen_pairs: set[tuple[int, int, str]] = set()
    for r in rows:
        sb, sc, sv = r["source_book"], r["source_chapter"], r["source_verse"]
        tb, tc, tv = r["target_book"], r["target_chapter"], r["target_verse"]
        if sv is None or tv is None or sc is None or tc is None:
            continue
        src_units = verse_to_units.get((sb, sc, sv))
        tgt_units = verse_to_units.get((tb, tc, tv))
        if not src_units or not tgt_units:
            continue
        link_type = (r["link_type"] or "reference").strip().lower().replace(" ", "_")
        edge_type = f"sefaria_{link_type}"
        for su in src_units:
            for tu in tgt_units:
                if su == tu:
                    continue
                key = (su, tu, edge_type)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                try:
                    cur.execute(
                        """
                        INSERT OR IGNORE INTO connection
                            (from_unit, to_unit, type, confidence, source)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (su, tu, edge_type, 0.6, "sefaria-import"),
                    )
                    if cur.rowcount:
                        inserted += 1
                except Exception as e:
                    print(f"  insert failed for {key}: {e}")
    conn.commit()
    print(f"  Inserted {inserted} sefaria-derived edges")
    return inserted


# ---------------------------------------------------------------------------
# Phase 2: Theographic enrichment
# ---------------------------------------------------------------------------

def _date_str(year_min: int | None, year_max: int | None) -> str | None:
    if year_min is None and year_max is None:
        return None
    if year_min is None:
        return f"≤{year_max}"
    if year_max is None or year_min == year_max:
        y = year_min
        return f"{abs(y)} BC" if y < 0 else f"{y} AD"
    return f"{abs(year_min)}–{abs(year_max)} BC" if year_min < 0 else f"{year_min}–{year_max} AD"


# Hand-curated overrides for multi-word/disambiguated names where exact-name match
# would pick the wrong row (e.g. "John" returns 4 rows; we want the Baptist).
PERSON_OVERRIDES = {
    "John The Baptist": "john_1676",
    "Mary Mother Of Jesus": "mary_1938",
}


def phase2_theographic(conn) -> int:
    print("\n=== Phase 2: Theographic enrichment of Person units ===")
    cur = conn.cursor()
    persons = cur.execute(
        "SELECT id, slug, title, frontmatter FROM unit WHERE type='person'"
    ).fetchall()
    enriched = 0
    skipped: list[str] = []
    for p in persons:
        name = p["title"]
        match = None
        # 1) Manual override.
        if name in PERSON_OVERRIDES:
            match = cur.execute(
                "SELECT * FROM theo_person WHERE id=?", (PERSON_OVERRIDES[name],)
            ).fetchone()
        # 2) Exact-name match (prefer rows with birth-year data).
        if not match:
            match = cur.execute(
                "SELECT * FROM theo_person WHERE LOWER(name)=LOWER(?) "
                "ORDER BY (minimum_birth_year IS NULL), id LIMIT 1",
                (name,),
            ).fetchone()
        # 3) Fall back to slug suffix.
        if not match:
            slug_name = p["slug"].split(":")[-1].replace("-", " ")
            match = cur.execute(
                "SELECT * FROM theo_person WHERE LOWER(name)=LOWER(?) LIMIT 1",
                (slug_name,),
            ).fetchone()
        if not match:
            skipped.append(name)
            continue

        # Look up place names.
        birth_place = None
        if match["birth_place_id"]:
            bp = cur.execute(
                "SELECT name, latitude, longitude FROM theo_place WHERE id=?",
                (match["birth_place_id"],),
            ).fetchone()
            if bp:
                birth_place = {"name": bp["name"], "lat": bp["latitude"], "lng": bp["longitude"]}

        death_place = None
        if match["death_place_id"]:
            dp = cur.execute(
                "SELECT name, latitude, longitude FROM theo_place WHERE id=?",
                (match["death_place_id"],),
            ).fetchone()
            if dp:
                death_place = {"name": dp["name"], "lat": dp["latitude"], "lng": dp["longitude"]}

        father_name = None
        if match["father_id"]:
            f = cur.execute("SELECT name FROM theo_person WHERE id=?", (match["father_id"],)).fetchone()
            father_name = f["name"] if f else None

        mother_name = None
        if match["mother_id"]:
            mo = cur.execute("SELECT name FROM theo_person WHERE id=?", (match["mother_id"],)).fetchone()
            mother_name = mo["name"] if mo else None

        enrichment = {
            "theographic_id": match["id"],
            "birth": _date_str(match["minimum_birth_year"], match["maximum_birth_year"]),
            "death": _date_str(match["minimum_death_year"], match["maximum_death_year"]),
            "birth_place": birth_place,
            "death_place": death_place,
            "father": father_name,
            "mother": mother_name,
            "gender": match["gender"],
            "summary": match["summary"],
        }

        # Merge into frontmatter under 'theographic' key.
        try:
            fm = json.loads(p["frontmatter"]) if p["frontmatter"] else {}
        except json.JSONDecodeError:
            fm = {}
        fm["theographic"] = enrichment
        cur.execute(
            "UPDATE unit SET frontmatter=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (json.dumps(fm, ensure_ascii=False), p["id"]),
        )
        enriched += 1
    conn.commit()
    print(f"  Enriched {enriched}/{len(persons)} person units")
    if skipped:
        print(f"  No theographic match for: {', '.join(skipped[:10])}"
              f"{'…' if len(skipped) > 10 else ''}")
    return enriched


# ---------------------------------------------------------------------------
# Phase 3: Shared-lexeme edges
# ---------------------------------------------------------------------------

RARE_THRESHOLD = 50  # global occurrences below this = "rare" lexeme

def phase3_shared_lexemes(conn) -> int:
    print("\n=== Phase 3: Shared-rare-lexeme edges ===")
    cur = conn.cursor()

    # Global Strong's frequency tables.
    print("  Counting Strong's frequencies…")
    heb_freq = dict(cur.execute(
        "SELECT strongs, COUNT(*) c FROM macula_hebrew_token "
        "WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs"
    ).fetchall())
    grk_freq = dict(cur.execute(
        "SELECT strongs, COUNT(*) c FROM macula_greek_token "
        "WHERE strongs IS NOT NULL AND strongs!='' GROUP BY strongs"
    ).fetchall())
    print(f"  Hebrew lexemes: {len(heb_freq)}, Greek lexemes: {len(grk_freq)}")

    # For each unit, collect all rare Strong's that appear in any verse of its refs.
    units = cur.execute("SELECT id, frontmatter FROM unit WHERE frontmatter IS NOT NULL").fetchall()
    unit_lexemes: dict[int, set[str]] = defaultdict(set)

    for u in units:
        try:
            fm = json.loads(u["frontmatter"])
        except json.JSONDecodeError:
            continue
        for key in ("ot_refs", "nt_refs", "refs"):
            for ref in fm.get(key) or []:
                parsed = parse_ref(str(ref))
                if not parsed:
                    continue
                book, chap, v1, v2 = parsed
                # Hebrew (OT)
                rows = cur.execute(
                    "SELECT DISTINCT strongs FROM macula_hebrew_token "
                    "WHERE book=? AND chapter=? AND verse BETWEEN ? AND ? "
                    "AND strongs IS NOT NULL AND strongs!=''",
                    (book[:3].upper() if False else book, chap, v1, v2),
                ).fetchall()
                # macula book codes are 3-letter uppercase ("GEN", "EXO", ...).
                # Try uppercase 3-letter abbrev if direct match returns nothing.
                if not rows:
                    code = _macula_book_code(book)
                    if code:
                        rows = cur.execute(
                            "SELECT DISTINCT strongs FROM macula_hebrew_token "
                            "WHERE book=? AND chapter=? AND verse BETWEEN ? AND ? "
                            "AND strongs IS NOT NULL AND strongs!=''",
                            (code, chap, v1, v2),
                        ).fetchall()
                for r in rows:
                    s = r["strongs"]
                    if heb_freq.get(s, 9999) < RARE_THRESHOLD:
                        unit_lexemes[u["id"]].add(s)
                # Greek (NT)
                code = _macula_book_code(book)
                if code:
                    rows = cur.execute(
                        "SELECT DISTINCT strongs FROM macula_greek_token "
                        "WHERE book=? AND chapter=? AND verse BETWEEN ? AND ? "
                        "AND strongs IS NOT NULL AND strongs!=''",
                        (code, chap, v1, v2),
                    ).fetchall()
                    for r in rows:
                        s = r["strongs"]
                        if grk_freq.get(s, 9999) < RARE_THRESHOLD:
                            unit_lexemes[u["id"]].add(s)

    print(f"  Units with rare lexemes: {len(unit_lexemes)}")
    # Invert: lexeme → units.
    lex_to_units: dict[str, set[int]] = defaultdict(set)
    for uid, lexset in unit_lexemes.items():
        for s in lexset:
            lex_to_units[s].add(uid)

    # Emit edges between every pair of units sharing each rare lexeme.
    inserted = 0
    seen: set[tuple[int, int]] = set()
    for strongs, uids in lex_to_units.items():
        if len(uids) < 2:
            continue
        uids_list = sorted(uids)
        for i, a in enumerate(uids_list):
            for b in uids_list[i + 1:]:
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                cur.execute(
                    """
                    INSERT OR IGNORE INTO connection
                        (from_unit, to_unit, type, confidence, source, evidence_md)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (a, b, "shares_lexeme", 0.5, "macula-import",
                     f"Shared rare Strong's: {strongs}"),
                )
                if cur.rowcount:
                    inserted += 1
    conn.commit()
    print(f"  Inserted {inserted} shares_lexeme edges")
    return inserted


MACULA_BOOK_CODES = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM",
    "Deuteronomy": "DEU", "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT",
    "I Samuel": "1SA", "II Samuel": "2SA", "I Kings": "1KI", "II Kings": "2KI",
    "I Chronicles": "1CH", "II Chronicles": "2CH", "Ezra": "EZR",
    "Nehemiah": "NEH", "Esther": "EST", "Job": "JOB", "Psalms": "PSA",
    "Proverbs": "PRO", "Ecclesiastes": "ECC", "Song of Songs": "SNG",
    "Isaiah": "ISA", "Jeremiah": "JER", "Lamentations": "LAM",
    "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS", "Joel": "JOL",
    "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC",
    "Nahum": "NAM", "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG",
    "Zechariah": "ZEC", "Malachi": "MAL", "Matthew": "MAT", "Mark": "MRK",
    "Luke": "LUK", "John": "JHN", "Acts": "ACT", "Romans": "ROM",
    "I Corinthians": "1CO", "II Corinthians": "2CO", "Galatians": "GAL",
    "Ephesians": "EPH", "Philippians": "PHP", "Colossians": "COL",
    "I Thessalonians": "1TH", "II Thessalonians": "2TH",
    "I Timothy": "1TI", "II Timothy": "2TI", "Titus": "TIT", "Philemon": "PHM",
    "Hebrews": "HEB", "James": "JAS", "I Peter": "1PE", "II Peter": "2PE",
    "I John": "1JN", "II John": "2JN", "III John": "3JN", "Jude": "JUD",
    "Revelation": "REV",
}


def _macula_book_code(canonical_book: str) -> str | None:
    return MACULA_BOOK_CODES.get(canonical_book)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 0], default=0,
                        help="Run one phase only (0=all)")
    args = parser.parse_args()
    conn = connect()
    before = conn.execute("SELECT COUNT(*) c FROM connection").fetchone()["c"]
    print(f"Connections before: {before}")

    if args.phase in (0, 1):
        phase1_sefaria_edges(conn)
    if args.phase in (0, 2):
        phase2_theographic(conn)
    if args.phase in (0, 3):
        phase3_shared_lexemes(conn)

    after = conn.execute("SELECT COUNT(*) c FROM connection").fetchone()["c"]
    print(f"\nConnections after:  {after}  (+{after - before})")
    conn.close()


if __name__ == "__main__":
    main()

"""Import the Theographic Bible Metadata dataset into bible_rag.db.

Source: https://github.com/robertrouse/theographic-bible-metadata (CC-BY 4.0)

Creates tables prefixed with theo_ so they live alongside our own units
without colliding. Idempotent: PRIMARY KEY on id + INSERT OR REPLACE.

Run with:  uv run python scripts/import_theographic.py
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_URL = "https://github.com/robertrouse/theographic-bible-metadata.git"
CLONE_DIR = Path("/tmp/theographic-bible-metadata")
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bible_rag.db"

# Raise CSV field size limit — some fields (e.g. dictText) are large.
csv.field_size_limit(sys.maxsize)


# ---------- schema ----------

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS theo_person (
        id TEXT PRIMARY KEY,
        name TEXT,
        alt_names TEXT,
        gender TEXT,
        minimum_birth_year INTEGER,
        maximum_birth_year INTEGER,
        minimum_death_year INTEGER,
        maximum_death_year INTEGER,
        birth_place_id TEXT,
        death_place_id TEXT,
        father_id TEXT,
        mother_id TEXT,
        summary TEXT,
        verses TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_place (
        id TEXT PRIMARY KEY,
        name TEXT,
        alt_names TEXT,
        feature_type TEXT,
        latitude REAL,
        longitude REAL,
        verses TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_event (
        id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        minimum_year INTEGER,
        maximum_year INTEGER,
        verses TEXT,
        participants TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_period (
        id TEXT PRIMARY KEY,
        name TEXT,
        start_year INTEGER,
        end_year INTEGER,
        description TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_group (
        id TEXT PRIMARY KEY,
        name TEXT,
        description TEXT,
        members TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_book (
        id TEXT PRIMARY KEY,
        name TEXT,
        short_name TEXT,
        testament TEXT,
        book_order INTEGER,
        chapter_count INTEGER,
        verse_count INTEGER,
        writers TEXT,
        raw TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS theo_easton (
        id TEXT PRIMARY KEY,
        term TEXT,
        text TEXT,
        person_lookup TEXT,
        place_lookup TEXT,
        raw TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_theo_person_name ON theo_person(name)",
    "CREATE INDEX IF NOT EXISTS idx_theo_place_name ON theo_place(name)",
    "CREATE INDEX IF NOT EXISTS idx_theo_event_name ON theo_event(name)",
    "CREATE INDEX IF NOT EXISTS idx_theo_book_name ON theo_book(name)",
]


# ---------- helpers ----------

def clone_repo() -> Path:
    if CLONE_DIR.exists() and (CLONE_DIR / "CSV").exists():
        return CLONE_DIR / "CSV"
    if CLONE_DIR.exists():
        shutil.rmtree(CLONE_DIR)
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(CLONE_DIR)],
        check=True,
    )
    return CLONE_DIR / "CSV"


def to_snake(name: str) -> str:
    name = name.lstrip("﻿").strip().strip('"')
    # camelCase -> snake_case
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            clean = {to_snake(k): (v if v != "" else None) for k, v in row.items() if k is not None}
            rows.append(clean)
        return rows


def to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        # handle decimal strings like "-4002.99"
        return int(float(v))
    except (ValueError, TypeError):
        return None


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def dumps_compact(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------- importers ----------

def import_people(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "People.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    for r in rows:
        pid = r.get("person_lookup") or r.get("person_i_d") or r.get("slug")
        if not pid:
            continue
        # Theographic semantics:
        #   birthYear / deathYear = canonical (best) estimates (negative = BC)
        #   minYear              = earliest plausible birth year (lower bound on birth)
        #   maxYear              = lifespan / age at death (years lived, not a year)
        # So a credible death-year bound is birthYear + maxYear.
        birth = to_int(r.get("birth_year"))
        death = to_int(r.get("death_year"))
        min_birth = to_int(r.get("min_year"))
        lifespan = to_int(r.get("max_year"))
        max_death = (birth + lifespan) if (birth is not None and lifespan is not None) else death
        payload.append((
            pid,
            r.get("name") or r.get("display_title"),
            r.get("also_called"),
            r.get("gender"),
            min_birth if min_birth is not None else birth,
            birth,
            death,
            max_death,
            r.get("birth_place"),
            r.get("death_place"),
            r.get("father"),
            r.get("mother"),
            r.get("dict_text"),
            r.get("verses"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_person
           (id, name, alt_names, gender, minimum_birth_year, maximum_birth_year,
            minimum_death_year, maximum_death_year, birth_place_id, death_place_id,
            father_id, mother_id, summary, verses, raw)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        payload,
    )
    return len(payload)


def import_places(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "Places.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    for r in rows:
        pid = r.get("place_lookup") or r.get("slug") or r.get("place_i_d")
        if not pid:
            continue
        # Prefer the verified open_bible_lat/long if present, else fallback latitude/longitude.
        lat = to_float(r.get("open_bible_lat")) or to_float(r.get("latitude"))
        lon = to_float(r.get("open_bible_long")) or to_float(r.get("longitude"))
        payload.append((
            pid,
            r.get("display_title") or r.get("kjv_name") or r.get("esv_name"),
            r.get("aliases"),
            r.get("feature_type"),
            lat,
            lon,
            r.get("verses"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_place
           (id, name, alt_names, feature_type, latitude, longitude, verses, raw)
           VALUES (?,?,?,?,?,?,?,?)""",
        payload,
    )
    return len(payload)


def import_events(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "Events.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    for r in rows:
        eid = r.get("event_i_d") or r.get("event_id") or r.get("title")
        if not eid:
            continue
        start = to_int(r.get("start_date"))
        # duration is like "7D" or "40Y" — parse trailing unit if possible to compute max_year.
        duration_raw = r.get("duration")
        max_year = start
        if start is not None and duration_raw:
            m = re.match(r"^(-?\d+)\s*([DWMY]?)", duration_raw.strip(), re.IGNORECASE)
            if m:
                n = int(m.group(1))
                unit = (m.group(2) or "Y").upper()
                if unit == "Y":
                    max_year = start + n
                # days/months don't change the year meaningfully here
        payload.append((
            str(eid),
            r.get("title"),
            r.get("notes"),
            start,
            max_year,
            r.get("verses"),
            r.get("participants"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_event
           (id, name, description, minimum_year, maximum_year, verses, participants, raw)
           VALUES (?,?,?,?,?,?,?,?)""",
        payload,
    )
    return len(payload)


def import_groups(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "PeopleGroups.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    for r in rows:
        name = r.get("group_name")
        if not name:
            continue
        gid = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        payload.append((
            gid,
            name,
            None,
            r.get("members"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_group
           (id, name, description, members, raw)
           VALUES (?,?,?,?,?)""",
        payload,
    )
    return len(payload)


def import_books(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "Books.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    for r in rows:
        bid = r.get("osis_name") or r.get("slug")
        if not bid:
            continue
        payload.append((
            bid,
            r.get("book_name"),
            r.get("short_name"),
            r.get("testament"),
            to_int(r.get("book_order")),
            to_int(r.get("chapter_count")),
            to_int(r.get("verse_count")),
            r.get("writers"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_book
           (id, name, short_name, testament, book_order, chapter_count, verse_count, writers, raw)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        payload,
    )
    return len(payload)


def import_easton(conn: sqlite3.Connection, csv_dir: Path) -> int:
    path = csv_dir / "Easton.csv"
    if not path.exists():
        print(f"  skip: {path.name} not found")
        return 0
    rows = read_csv(path)
    payload = []
    seen: set[str] = set()
    for i, r in enumerate(rows):
        tid = r.get("term_i_d") or r.get("term_id")
        # term_id can repeat with itemNum; build composite id.
        item = r.get("item_num") or ""
        eid = f"{tid}_{item}" if tid else None
        if not eid:
            eid = f"easton_{i}"
        if eid in seen:
            eid = f"{eid}_{i}"
        seen.add(eid)
        payload.append((
            eid,
            r.get("term_label") or r.get("dict_lookup"),
            r.get("dict_text"),
            r.get("person_lookup"),
            r.get("place_lookup"),
            dumps_compact(r),
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO theo_easton
           (id, term, text, person_lookup, place_lookup, raw)
           VALUES (?,?,?,?,?,?)""",
        payload,
    )
    return len(payload)


# ---------- main ----------

def main() -> None:
    print(f"DB: {DB_PATH}")
    if not DB_PATH.exists():
        sys.exit(f"DB not found at {DB_PATH}")

    print("Cloning / locating Theographic repo...")
    csv_dir = clone_repo()
    print(f"  CSVs at: {csv_dir}")

    conn = sqlite3.connect(DB_PATH)
    try:
        for stmt in SCHEMA:
            conn.execute(stmt)
        conn.commit()

        importers = [
            ("theo_person", import_people),
            ("theo_place", import_places),
            ("theo_event", import_events),
            ("theo_group", import_groups),
            ("theo_book", import_books),
            ("theo_easton", import_easton),
        ]
        counts = {}
        for table, fn in importers:
            print(f"Importing {table}...")
            try:
                n = fn(conn, csv_dir)
                conn.commit()
                counts[table] = n
                print(f"  -> {n} rows")
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                print(f"  !! failed: {e}")
                counts[table] = f"ERROR: {e}"

        # theo_period intentionally empty — Theographic does not ship a periods CSV.
        counts["theo_period"] = 0
        print("\nFinal counts:")
        for t, n in counts.items():
            print(f"  {t}: {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

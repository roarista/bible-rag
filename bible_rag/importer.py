"""Import markdown seeds/symbols/motifs from the vault into the DB.

Source of truth for content = markdown files in the Obsidian vault.
This importer parses frontmatter + body, populates `unit`, then resolves
wikilinks/frontmatter references into typed `connection` rows.

Re-running is idempotent: existing units are upserted by slug, and
connections are recomputed from scratch on each run.
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import frontmatter

from . import VAULT_PATH


# Folders in the vault that the importer treats as unit sources
UNIT_SOURCES = {
    "Seeds":       "seed",
    "Symbols":     "symbol",
    "Motifs":      "motif",
    "Persons":     "person",
    "Places":      "place",
    "Numbers":     "number",
    "Titles":      "title",
    "Structures":  "structure",
    "Covenants":   "covenant",
    "Festivals":   "festival",
    "Miracles":    "miracle",
    "Parables":    "parable",
    "Prophecies":  "prophecy",
    "Theophanies": "theophany",
    "Offices":     "office",
    "Lexemes":     "lexeme",
}

# Files to skip even if present in a unit folder
SKIP_NAMES = {"README.md", "_index.md"}

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


def slug_for(unit_type: str, file_stem: str) -> str:
    return f"{unit_type}:{file_stem}"


def parse_unit_file(path: Path, unit_type: str) -> dict:
    post = frontmatter.load(path)
    fm = dict(post.metadata)
    body = post.content
    title = path.stem.replace("-", " ")
    return {
        "type":        unit_type,
        "slug":        slug_for(unit_type, path.stem),
        "title":       title,
        "status":      fm.get("status"),
        "confidence":  fm.get("confidence"),
        "language":    fm.get("language"),
        "source_path": str(path),
        "frontmatter": json.dumps(fm, default=str),
        "body_md":     body,
        "_raw_fm":     fm,
        "_stem":       path.stem,
    }


def upsert_unit(conn: sqlite3.Connection, unit: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO unit (type, slug, title, status, confidence, language,
                          source_path, frontmatter, body_md, updated_at)
        VALUES (:type, :slug, :title, :status, :confidence, :language,
                :source_path, :frontmatter, :body_md, CURRENT_TIMESTAMP)
        ON CONFLICT(slug) DO UPDATE SET
            title       = excluded.title,
            status      = excluded.status,
            confidence  = excluded.confidence,
            language    = excluded.language,
            source_path = excluded.source_path,
            frontmatter = excluded.frontmatter,
            body_md     = excluded.body_md,
            updated_at  = CURRENT_TIMESTAMP
        RETURNING id
        """,
        {k: v for k, v in unit.items() if not k.startswith("_")},
    )
    return cur.fetchone()[0]


def iter_unit_files() -> Iterable[tuple[Path, str]]:
    for folder, unit_type in UNIT_SOURCES.items():
        d = VAULT_PATH / folder
        if not d.exists():
            continue
        for md in sorted(d.glob("*.md")):
            if md.name in SKIP_NAMES:
                continue
            yield md, unit_type


def resolve_slug(target_stem: str, units_by_stem: dict[str, dict]) -> str | None:
    """Given a wikilink target like 'Lamb' or '../Symbols/Lamb', return canonical slug."""
    stem = Path(target_stem).stem
    return units_by_stem.get(stem, {}).get("slug")


def extract_connections(unit: dict, units_by_stem: dict[str, dict]) -> list[dict]:
    """Pull typed connections from a unit's frontmatter + body wikilinks."""
    out: list[dict] = []
    fm = unit["_raw_fm"]
    from_slug = unit["slug"]

    # Frontmatter-declared references (highest fidelity)
    fm_ref_types = [
        ("symbols",     "uses_symbol"),
        ("motifs",      "has_motif"),
        ("persons",     "references_person"),
        ("places",      "references_place"),
        ("numbers",     "references_number"),
        ("titles",      "references_title"),
        ("structures",  "references_structure"),
        ("covenants",   "references_covenant"),
        ("festivals",   "references_festival"),
        ("miracles",    "references_miracle"),
        ("parables",    "references_parable"),
        ("prophecies",  "references_prophecy"),
        ("theophanies", "references_theophany"),
        ("offices",     "references_office"),
        ("lexemes",     "uses_lexeme"),
    ]
    for fm_key, conn_type in fm_ref_types:
        for ref in fm.get(fm_key) or []:
            target = resolve_slug(ref, units_by_stem)
            if target:
                out.append({"from": from_slug, "to": target, "type": conn_type,
                            "confidence": 1.0, "source": "seed"})

    # Body wikilinks fall into "references" (weaker, mostly to external notes)
    for m in WIKILINK_RE.finditer(unit["body_md"]):
        raw = m.group(1).strip()
        target = resolve_slug(raw, units_by_stem)
        if target and target != from_slug:
            out.append({"from": from_slug, "to": target, "type": "references",
                        "confidence": 0.6, "source": "seed"})
    return out


def get_unit_id_by_slug(conn: sqlite3.Connection, slug: str) -> int | None:
    row = conn.execute("SELECT id FROM unit WHERE slug = ?", (slug,)).fetchone()
    return row["id"] if row else None


def upsert_connection(conn: sqlite3.Connection, c: dict) -> None:
    from_id = get_unit_id_by_slug(conn, c["from"])
    to_id = get_unit_id_by_slug(conn, c["to"])
    if not from_id or not to_id:
        return
    conn.execute(
        """
        INSERT INTO connection (from_unit, to_unit, type, confidence, source)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(from_unit, to_unit, type) DO UPDATE SET
            confidence = excluded.confidence,
            source     = excluded.source
        """,
        (from_id, to_id, c["type"], c["confidence"], c["source"]),
    )


def import_all(conn: sqlite3.Connection) -> dict:
    """Run a full import. Returns counts."""
    # Pass 1: load all unit files (so wikilink resolution can see siblings)
    units: list[dict] = []
    for path, unit_type in iter_unit_files():
        units.append(parse_unit_file(path, unit_type))

    units_by_stem = {u["_stem"]: u for u in units}

    # Pass 2: upsert units
    for u in units:
        upsert_unit(conn, u)

    # Pass 3: rebuild connections from the curated seed data
    conn.execute("DELETE FROM connection WHERE source = 'seed'")
    n_conns = 0
    for u in units:
        for c in extract_connections(u, units_by_stem):
            upsert_connection(conn, c)
            n_conns += 1

    conn.commit()
    return {
        "units":       len(units),
        "by_type":     {t: sum(1 for u in units if u["type"] == t)
                        for t in set(u["type"] for u in units)},
        "connections": n_conns,
    }

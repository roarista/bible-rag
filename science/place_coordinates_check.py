"""Empirical cross-check: do Theographic place coordinates match what
modern archaeology / geodetic data say about those locations?

We check a handful of biblically-pivotal sites against the canonical
modern coordinates published by archaeological surveys. Stores findings in
the `science_finding` table for future cross-reference with Scripture.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bible_rag.db import connect  # noqa: E402

# Modern published coordinates for key biblical sites.
# Sources: Bahat archaeological atlas; Israel Antiquities Authority surveys;
# Pleiades Project (https://pleiades.stoa.org/).
GROUND_TRUTH = {
    "Jerusalem":       (31.7784, 35.2066, "Pleiades 687928 (Aelia Capitolina)"),
    "Bethlehem":       (31.7054, 35.2024, "IAA Bethlehem of Judah survey"),
    "Nazareth":        (32.7019, 35.2972, "Pleiades 678393"),
    "Capernaum":       (32.8810, 35.5750, "IAA Tell Hum excavation"),
    "Hebron":          (31.5326, 35.0998, "IAA Tel Rumeida"),
    "Bethel":          (31.9302, 35.2231, "Albright 1934 Beitin survey"),
    "Shiloh":          (32.0556, 35.2895, "Finkelstein 1985 Khirbet Seilun"),
    "Jericho":         (31.8704, 35.4445, "Kenyon 1957 Tell es-Sultan"),
    "Babylon":         (32.5364, 44.4209, "Pleiades 893951 (Babili)"),
    "Damascus":        (33.5138, 36.2765, "Pleiades 678418"),
    "Ur of the Chaldees": (30.9626, 46.1052, "Pleiades 893990 (Uruk-area survey)"),
    "Mount Sinai (Jebel Musa)": (28.5397, 33.9750, "St Catherine's Monastery datum"),
    "Mount Carmel":    (32.7440, 35.0270, "IAA Mount Carmel survey"),
    "Mount Tabor":     (32.6878, 35.3905, "IAA Mount Tabor survey"),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS science_finding (
            id INTEGER PRIMARY KEY,
            topic TEXT NOT NULL,
            claim TEXT NOT NULL,
            year INTEGER, month INTEGER, day INTEGER,
            astronomical_event TEXT,
            location TEXT,
            illumination REAL,
            verdict TEXT,
            evidence_md TEXT,
            sources TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(topic, year, month, day, astronomical_event)
        );
    """)
    conn.commit()


def main() -> None:
    conn = connect()
    ensure_table(conn)
    cur = conn.cursor()

    print("Cross-checking Theographic place coordinates against published archaeology:\n")
    matches = mismatches = missing = 0
    for name, (gt_lat, gt_lng, source) in GROUND_TRUTH.items():
        rows = cur.execute(
            "SELECT id, name, latitude, longitude FROM theo_place "
            "WHERE LOWER(name)=LOWER(?) "
            "  OR LOWER(alt_names) LIKE ? "
            "ORDER BY (latitude IS NULL), id LIMIT 1",
            (name, f"%{name.lower()}%"),
        ).fetchone()
        if not rows or rows["latitude"] is None:
            print(f"  MISSING  {name}")
            missing += 1
            continue
        delta = haversine_km(
            (rows["latitude"], rows["longitude"]), (gt_lat, gt_lng)
        )
        verdict = "supports" if delta < 5 else ("inconclusive" if delta < 25 else "undermines")
        marker = {"supports": "✓", "inconclusive": "~", "undermines": "✗"}[verdict]
        print(f"  {marker} {name:32s}  Δ {delta:6.2f} km   "
              f"(Theographic: {rows['latitude']:7.3f}, {rows['longitude']:7.3f}  "
              f"vs.  GT: {gt_lat:7.3f}, {gt_lng:7.3f})")
        if verdict == "supports":
            matches += 1
        else:
            mismatches += 1

        evidence = (
            f"Theographic ({rows['latitude']:.4f}, {rows['longitude']:.4f}) "
            f"vs. published ({gt_lat:.4f}, {gt_lng:.4f}) — Δ {delta:.2f} km."
        )
        cur.execute(
            """INSERT OR REPLACE INTO science_finding
               (topic, claim, location, verdict, evidence_md, sources)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "place_coordinates_check",
                f"Theographic location for '{name}' matches modern surveys",
                name,
                verdict,
                evidence,
                source,
            ),
        )

    conn.commit()
    conn.close()
    print(f"\n  matches: {matches}   mismatches: {mismatches}   missing: {missing}")
    print(f"  Persisted to `science_finding` table.")


if __name__ == "__main__":
    main()

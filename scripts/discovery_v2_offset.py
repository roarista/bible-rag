"""Discovery V2 — offset-vector typology.

Word2vec analogy intuition: if Adam→Christ encodes a 'last-Adam' vector, then
any other OT figure who's an Adamic type should have a similar offset to its
NT counterpart.

Strategy:
  1. For every pair of seeds connected through ≥2 SHARED motifs or symbols,
     compute their embedding offset (B - A).
  2. Cluster these offsets into 'typology axes' (k-means, k=8).
  3. For each axis, find the centroid offset.
  4. For each seed A, predict A_NT ≈ A + centroid_k for each axis k.
  5. Search for unconnected seeds B near the predicted point.
  6. Emit as `offset_echo` edges with the axis label as evidence.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from bible_rag.db import connect  # noqa: E402

TOP_N = 500
K_AXES = 8


def load_embeddings(conn: sqlite3.Connection) -> tuple[dict[int, np.ndarray], dict[int, dict]]:
    """Returns {unit_id → vec} and {unit_id → unit_row}."""
    rows = conn.execute(
        "SELECT u.id, u.slug, u.type, u.title, u.frontmatter, v.vector "
        "FROM unit u "
        "JOIN embedding_meta m ON m.unit_id=u.id "
        "JOIN embedding_vec v ON v.embedding_id=m.id"
    ).fetchall()
    vecs = {}
    meta = {}
    for r in rows:
        v = np.frombuffer(r["vector"], dtype=np.float32)
        # Normalize for cosine.
        n = np.linalg.norm(v)
        if n > 0:
            v = v / n
        vecs[r["id"]] = v
        meta[r["id"]] = {
            "slug": r["slug"], "type": r["type"], "title": r["title"],
            "frontmatter": r["frontmatter"],
        }
    return vecs, meta


def shared_motif_pairs(conn: sqlite3.Connection) -> dict[tuple[int, int], int]:
    """Return seed-pairs with their shared (motif + symbol) count."""
    rows = conn.execute(
        "SELECT from_unit AS seed_id, to_unit AS anchor_id "
        "FROM connection WHERE type IN ('has_motif', 'uses_symbol')"
    ).fetchall()
    seed_to_anchors: dict[int, set[int]] = defaultdict(set)
    for r in rows:
        seed_to_anchors[r["seed_id"]].add(r["anchor_id"])

    seeds = sorted(seed_to_anchors.keys())
    pair_count: dict[tuple[int, int], int] = {}
    for i, a in enumerate(seeds):
        for b in seeds[i+1:]:
            shared = seed_to_anchors[a] & seed_to_anchors[b]
            if len(shared) >= 2:
                pair_count[(a, b)] = len(shared)
    return pair_count


def existing_pairs(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    pairs = set()
    for r in conn.execute("SELECT from_unit, to_unit FROM connection"):
        pairs.add(tuple(sorted((r["from_unit"], r["to_unit"]))))
    return pairs


def main() -> None:
    conn = connect()

    print("Loading embeddings…")
    vecs, meta = load_embeddings(conn)
    print(f"  {len(vecs)} unit embeddings (dim={next(iter(vecs.values())).shape[0]})")

    print("Finding shared-motif/symbol seed pairs…")
    motif_pairs = shared_motif_pairs(conn)
    print(f"  {len(motif_pairs)} pairs share ≥2 motifs/symbols")

    # Compute offsets for connected motif-pairs (these ARE typology pairs).
    offsets = []
    for (a, b), n_shared in motif_pairs.items():
        if a not in vecs or b not in vecs:
            continue
        offsets.append((vecs[b] - vecs[a], a, b, n_shared))
    print(f"  computed {len(offsets)} offset vectors")

    if len(offsets) < K_AXES:
        print("  not enough offsets for clustering; bailing")
        return

    # Simple k-means on offsets to find K_AXES typology axes.
    X = np.stack([o[0] for o in offsets])
    rng = np.random.default_rng(42)
    # Seed centroids with random points
    centroids = X[rng.choice(len(X), size=K_AXES, replace=False)]
    for it in range(20):
        # Assign
        sims = X @ centroids.T  # cosine since normalized-ish
        labels = sims.argmax(axis=1)
        new_centroids = np.stack([
            X[labels == k].mean(axis=0) if (labels == k).any() else centroids[k]
            for k in range(K_AXES)
        ])
        # Renormalize centroids to unit length
        norms = np.linalg.norm(new_centroids, axis=1, keepdims=True)
        norms[norms == 0] = 1
        new_centroids = new_centroids / norms
        diff = np.linalg.norm(new_centroids - centroids)
        centroids = new_centroids
        if diff < 1e-4:
            break
    print(f"  k-means converged after {it+1} iterations")

    # Label each axis with the top contributing seed-pairs to understand what it represents.
    axis_label: dict[int, str] = {}
    for k in range(K_AXES):
        members = [offsets[i] for i in range(len(offsets)) if labels[i] == k]
        if not members:
            axis_label[k] = f"axis_{k}_empty"
            continue
        # Top 3 most-central members
        member_offsets = np.stack([m[0] for m in members])
        sims_to_centroid = member_offsets @ centroids[k]
        top = sorted(range(len(members)), key=lambda i: -sims_to_centroid[i])[:3]
        names = []
        for ti in top:
            _, aid, bid, _ = members[ti]
            names.append(f"{meta[aid]['title']}→{meta[bid]['title']}")
        axis_label[k] = " | ".join(names)
        print(f"  axis {k} ({len(members)} pairs): {axis_label[k]}")

    # For each axis, search for unconnected seed-pairs whose offset matches the axis centroid.
    existing = existing_pairs(conn)
    seed_ids = [uid for uid, m in meta.items() if m["type"] in
                {"seed", "person", "prophecy", "miracle", "covenant",
                 "festival", "parable", "theophany"}]
    print(f"  searching across {len(seed_ids)} typology-rich units")

    # Build embedding matrix for fast similarity
    seed_ids_arr = np.array(seed_ids)
    E = np.stack([vecs[i] for i in seed_ids])

    candidates: list[tuple[float, int, int, int, str]] = []  # (score, a, b, axis, label)
    for a in seed_ids:
        a_vec = vecs[a]
        for k in range(K_AXES):
            predicted = a_vec + centroids[k]
            pred_norm = predicted / max(np.linalg.norm(predicted), 1e-9)
            sims = E @ pred_norm
            # Top 3 candidates per axis per seed
            top_idx = np.argpartition(-sims, 3)[:3]
            for ti in top_idx:
                b = int(seed_ids_arr[ti])
                if b == a:
                    continue
                pair = tuple(sorted((a, b)))
                if pair in existing:
                    continue
                # Also require: the actual observed offset must point in the axis direction.
                obs = vecs[b] - a_vec
                obs_norm = obs / max(np.linalg.norm(obs), 1e-9)
                axis_alignment = float(obs_norm @ centroids[k])
                if axis_alignment < 0.4:
                    continue
                score = float(sims[ti]) * 0.5 + axis_alignment * 0.5
                candidates.append((score, a, b, k, axis_label[k]))

    # Dedup by pair (keep best axis match per pair)
    best_per_pair: dict[tuple[int, int], tuple[float, int, int, int, str]] = {}
    for c in candidates:
        score, a, b, k, lbl = c
        pair = tuple(sorted((a, b)))
        if pair not in best_per_pair or best_per_pair[pair][0] < score:
            best_per_pair[pair] = c

    ranked = sorted(best_per_pair.values(), reverse=True)[:TOP_N]
    print(f"\n  {len(best_per_pair)} unique candidate pairs, taking top {len(ranked)}")

    # Persist as offset_echo edges
    cur = conn.cursor()
    inserted = 0
    for score, a, b, k, lbl in ranked:
        ev = f"axis={k} | sim={score:.3f} | repr_pairs={lbl[:200]}"
        cur.execute(
            """INSERT OR IGNORE INTO connection
               (from_unit, to_unit, type, confidence, source, evidence_md,
                score_status, score)
               VALUES (?, ?, 'offset_echo', ?, 'discovery-v2', ?, 'candidate', ?)""",
            (a, b, score, ev, score),
        )
        if cur.rowcount:
            inserted += 1
    conn.commit()
    print(f"\nInserted {inserted} offset_echo candidates")

    # Preview
    print("\nTop 15 offset-vector candidates:")
    rows = cur.execute(
        "SELECT c.score, u1.title AS a, u2.title AS b, c.evidence_md "
        "FROM connection c "
        "JOIN unit u1 ON u1.id=c.from_unit "
        "JOIN unit u2 ON u2.id=c.to_unit "
        "WHERE c.type='offset_echo' "
        "ORDER BY c.score DESC LIMIT 15"
    ).fetchall()
    for r in rows:
        print(f"  {r['score']:.3f}  {r['a']} → {r['b']}")
        print(f"        {r['evidence_md'][:150]}")
    conn.close()


if __name__ == "__main__":
    main()

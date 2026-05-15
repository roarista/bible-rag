# Science Module — Separate from the Bible RAG

This directory is **architecturally separate** from the main Bible RAG.

## Why separate?

The Bible RAG (`bible_rag/`) is a typological/thematic graph of **Scripture only** —
the inspired text plus established interpretive traditions (Sefaria, MACULA, Theographic,
seed library). Its visualization (`/`, `/3d`) and content model are tuned for that scope.

Adding modern-science findings (astronomy, archaeology, paleography, geology)
directly into the same graph would:
1. Mix epistemological categories — internal canonical evidence vs. external empirical
   evidence collapse into a single dimension when they shouldn't.
2. Overwhelm the visualization — the graph is already dense with ~3k legible edges;
   layering empirical citations on top would obscure the typology view.
3. Tie content to data sources that update on different cycles.

So `science/` is intentionally a **second module** that:
- Reads from the same database (specifically the `science_finding` table) and
  cross-references Scripture by verse-range
- Has its own runners under `science/`, not in `scripts/`
- Will eventually have its own UI surface (probably `/evidence`) when we build it,
  with its own theme/layout suited for empirical-claims display

## What lives here

| File | Purpose |
|---|---|
| `crucifixion_eclipse.py` | Skyfield + JPL DE422 check on Passover full-moon constraint for AD 30–34 |
| `place_coordinates_check.py` | Cross-reference Theographic place coordinates with Pleiades gazetteer / OpenStreetMap |

The `science_finding` table in the main DB stores results so the future evidence
page can join them with Scripture context, but the main graph (`/api/graph`) does
NOT include them.

## Running

```bash
uv run python science/crucifixion_eclipse.py
uv run python science/place_coordinates_check.py
```

Each script writes to `science_finding`. To inspect:

```sql
SELECT topic, verdict, evidence_md, sources FROM science_finding;
```

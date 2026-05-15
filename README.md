# Bible RAG

**A multi-scale, multilingual, typology-aware retrieval system for the Bible.**
Discovers structural connections between OT stories and NT fulfillment using semantic embeddings, a curated typology seed library, and adversarial multi-agent contestation.

> Not a translation tool. Not a verse-search tool. A **meaning graph** for scripture.

## Why this exists

Most "Bible RAG" projects index verses and let you do nearest-neighbor search on translated text. That finds verses with similar surface vocabulary. It misses the deeper structure that makes scripture coherent: **typological foreshadowing**, where OT stories prefigure NT fulfillment in patterns that span centuries.

Examples this system is designed to find and stress-test:

- **Abraham almost sacrificing Isaac** (Genesis 22) → **God offering his Son** at Calvary
- **Joseph's cellmates** (bread, wine, hanged on a tree, third day) → **two thieves on the cross**
- **Passover lamb's blood on the doorposts** → **Christ's blood covering believers**
- **Jonah three days in the fish** → **three days in the tomb** (Jesus' own typology, Mt 12:40)
- **Bronze serpent lifted on a pole** → **Christ "lifted up"** (Jesus' own typology, John 3:14)
- **The genealogy from Adam to Noah**, where the meanings of the ten Hebrew names form a sentence that reads as the gospel
- **And typologies no one has noticed yet** — surfaced by autonomous discovery agents, attacked by multi-model skeptic agents, only the survivors presented

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│  SOURCE LAYER (markdown, in an Obsidian vault)                    │
│  Seeds/       — curated typologies (humans write these)           │
│  Symbols/     — shared cross-references (lamb, blood, three-days) │
│  Motifs/      — theological patterns (substitution, redemption)   │
└───────────────────────────────────────────────────────────────────┘
                          │ importer
                          ▼
┌───────────────────────────────────────────────────────────────────┐
│  ENGINE LAYER (SQLite + sqlite-vec)                               │
│  unit           — typed nodes (seed/symbol/motif/pericope/verse)  │
│  connection     — typed edges (uses_symbol, foreshadows, ...)     │
│  scripture      — verse-level text in 4+ languages                │
│  embedding_vec  — 3072-dim vectors (text-embedding-3-large)       │
│  unit_fts       — FTS5 full-text search                           │
└───────────────────────────────────────────────────────────────────┘
                          │ query.py
                          ▼
┌───────────────────────────────────────────────────────────────────┐
│  AGENT LAYER (Claude)                                             │
│  Surfacer  → Steelman → 4 Skeptics → Synthesizer → Presenter      │
│  Skeptics run on different model families to avoid blind spots    │
└───────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────────┐
│  INTERFACE LAYER                                                  │
│  • Chat (REPL or Claude conversation)                             │
│  • Graph visualization (Cytoscape.js web app — coming)            │
│  • Daily discovery feed (markdown notes auto-written to vault)    │
└───────────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
git clone https://github.com/YOUR-USERNAME/bible-rag.git
cd bible-rag

# Install with uv (https://docs.astral.sh/uv/)
uv sync

# Set up your API keys
cp .env.example .env
# edit .env and add OPENAI_API_KEY (for embeddings)
# and ANTHROPIC_API_KEY (for the agent layer, when implemented)

# Build the DB from the seed library
uv run python scripts/build.py

# Or build + embed all units
uv run python scripts/build.py --embed

# Run the demo (graph hubs, FTS, semantic search)
uv run python scripts/demo.py
```

## Multilingual corpus

The system loads the Bible in four languages from authoritative sources:

| Language | Source | License |
|---|---|---|
| Biblical Hebrew + Aramaic | [ETCBC/BHSA](https://github.com/ETCBC/bhsa) via Text-Fabric | CC-BY |
| Koine Greek | [CenterBLC/N1904](https://github.com/CenterBLC/N1904) via Text-Fabric | CC-BY |
| English | World English Bible via [bible-api.com](https://bible-api.com) | Public Domain |
| Spanish | RVA (planned) | Public Domain |

Original languages are used as **feature engineering** for connection discovery — shared lexical roots, morphology, and semantic domains feed the embedding signal. The user interface speaks English/Spanish unless deeper exploration is requested.

## Seed library (current state)

12 hand-curated typologies + 9 symbols + 4 motifs. Each seed includes:
- OT story summary + scripture refs
- NT fulfillment + scripture refs
- Shared structural beats
- Counterarguments and skeptical readings (load-bearing — typologies are surfaced *with* their attack log)
- Sources (canonical, patristic, modern)
- "Embedding hint" — what pattern shape the system should learn from this example

The library aims for **40-80 high-quality seeds**. Quality > quantity. A weak seed teaches the system to find weak patterns.

## Methodological discipline

This system surfaces candidates; **it does not assert truth**. Every surfaced connection comes with:
1. The structural argument for why it's a typology
2. Lexical evidence in original languages
3. Skeptic agent attacks (textual / historical / theological / methodological)
4. A confidence score

The reader judges, in prayer and with the church. The system is a research assistant operating at scale, not an oracle.

## Contributing

This project is intentionally open. Bible scholars, linguists, RAG engineers, and theologians are welcome to fork, modify, contribute seeds, build alternative visualizations, or rebuild from scratch with better infrastructure.

If you contribute a seed:
- Use the template in `Seeds/README.md`
- Include counterarguments — typologies without contestation are not helpful
- Cite at least one canonical, patristic, or modern source
- Submit as a PR with the markdown file + an entry in `Seeds/README.md`'s index

## Status

**2026-05-15** — Engine operational. 12 seeds loaded. Embeddings ready (needs API key). Web visualization in progress. See `Bible-RAG/Run-Log.md` in the vault for the running build log.

## License

MIT — see `LICENSE`.

The biblical corpora used (BHSA, N1904, WEB) carry their own licenses, which permit redistribution and modification under the terms cited above.

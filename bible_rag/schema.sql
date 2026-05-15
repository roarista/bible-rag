-- Bible RAG schema
-- Nodes are universal "units of meaning"; edges are typed connections.
-- The markdown files in the vault are the source of truth for content;
-- this DB is the queryable engine on top.

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ----------------------------------------------------------------------
-- UNIT: every meaning-bearing node in the graph
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS unit (
    id              INTEGER PRIMARY KEY,
    type            TEXT    NOT NULL,        -- seed | symbol | motif | pericope | verse | lexeme | evidence
    slug            TEXT    NOT NULL UNIQUE, -- e.g. 'seed:Abraham-Isaac', 'symbol:Lamb', 'verse:Genesis-22-2'
    title           TEXT    NOT NULL,
    status          TEXT,                    -- foundational | candidate | refuted
    confidence      TEXT,                    -- high | medium-high | medium | low
    language        TEXT,                    -- en | es | he | gr | aram | mixed
    source_path     TEXT,                    -- path to source markdown if any
    frontmatter     TEXT,                    -- raw YAML frontmatter as JSON
    body_md         TEXT,                    -- markdown body
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_unit_type ON unit(type);
CREATE INDEX IF NOT EXISTS idx_unit_status ON unit(status);

-- ----------------------------------------------------------------------
-- CONNECTION: typed edges between units
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connection (
    id              INTEGER PRIMARY KEY,
    from_unit       INTEGER NOT NULL REFERENCES unit(id) ON DELETE CASCADE,
    to_unit         INTEGER NOT NULL REFERENCES unit(id) ON DELETE CASCADE,
    type            TEXT    NOT NULL,
        -- uses_symbol      : seed → symbol
        -- has_motif        : seed → motif
        -- foreshadows      : pericope/seed → pericope/seed (OT prefigures NT)
        -- fulfills         : pericope → pericope (NT fulfills OT)
        -- cites            : pericope → pericope (one quotes the other)
        -- parallels        : pericope ↔ pericope (structural mirror)
        -- lexical_echo     : verse ↔ verse (shared original-language root)
        -- references       : seed/pericope → verse
        -- personal_link    : seed → external (Christian/ folder)
    confidence      REAL DEFAULT 1.0,        -- 0.0–1.0
    evidence_md     TEXT,                    -- markdown describing the connection
    contestation_md TEXT,                    -- attack log from skeptic agents
    source          TEXT,                    -- 'seed' (human-curated) | 'discovered' (agent-found)
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_unit, to_unit, type)
);

CREATE INDEX IF NOT EXISTS idx_conn_from ON connection(from_unit, type);
CREATE INDEX IF NOT EXISTS idx_conn_to   ON connection(to_unit, type);
CREATE INDEX IF NOT EXISTS idx_conn_type ON connection(type);
CREATE INDEX IF NOT EXISTS idx_conn_source ON connection(source);

-- ----------------------------------------------------------------------
-- SCRIPTURE: verse-level text, multi-language
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scripture (
    id              INTEGER PRIMARY KEY,
    book            TEXT    NOT NULL,        -- 'Genesis', 'Isaiah', 'John', etc.
    chapter         INTEGER NOT NULL,
    verse           INTEGER NOT NULL,
    language        TEXT    NOT NULL,        -- he | aram | gr | en | es
    version         TEXT    NOT NULL,        -- 'BHSA' | 'N1904' | 'WEB' | 'RVA' etc.
    text            TEXT    NOT NULL,
    lemma_json      TEXT,                    -- per-word lemmas/morphology where available
    UNIQUE(book, chapter, verse, language, version)
);

CREATE INDEX IF NOT EXISTS idx_scripture_ref ON scripture(book, chapter, verse);

-- ----------------------------------------------------------------------
-- LEXEME: original-language word entries with cross-references
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lexeme (
    id              INTEGER PRIMARY KEY,
    language        TEXT    NOT NULL,        -- he | aram | gr
    lemma           TEXT    NOT NULL,        -- canonical form (e.g. חלל, ἀμνός)
    strong_number   TEXT,                    -- 'H2490', 'G286', etc.
    gloss_en        TEXT,
    gloss_es        TEXT,
    semantic_domain TEXT,
    UNIQUE(language, lemma)
);

CREATE INDEX IF NOT EXISTS idx_lex_lemma ON lexeme(lemma);
CREATE INDEX IF NOT EXISTS idx_lex_strong ON lexeme(strong_number);

-- ----------------------------------------------------------------------
-- EMBEDDING: vector storage (sqlite-vec)
-- Stores embeddings per unit at one or more scales.
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS embedding_meta (
    id              INTEGER PRIMARY KEY,
    unit_id         INTEGER NOT NULL REFERENCES unit(id) ON DELETE CASCADE,
    model           TEXT    NOT NULL,        -- 'text-embedding-3-large'
    scale           TEXT    NOT NULL,        -- 'word' | 'verse' | 'pericope' | 'seed'
    input_text      TEXT    NOT NULL,        -- what was actually embedded
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(unit_id, model, scale)
);

-- The vector itself is in a virtual table created at runtime via sqlite-vec
-- See db.py:init_vec_table()

-- ----------------------------------------------------------------------
-- FULL-TEXT SEARCH over unit content
-- ----------------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS unit_fts USING fts5(
    title,
    body_md,
    content='unit',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS unit_fts_insert AFTER INSERT ON unit BEGIN
    INSERT INTO unit_fts(rowid, title, body_md) VALUES (new.id, new.title, new.body_md);
END;
CREATE TRIGGER IF NOT EXISTS unit_fts_delete AFTER DELETE ON unit BEGIN
    INSERT INTO unit_fts(unit_fts, rowid, title, body_md) VALUES('delete', old.id, old.title, old.body_md);
END;
CREATE TRIGGER IF NOT EXISTS unit_fts_update AFTER UPDATE ON unit BEGIN
    INSERT INTO unit_fts(unit_fts, rowid, title, body_md) VALUES('delete', old.id, old.title, old.body_md);
    INSERT INTO unit_fts(rowid, title, body_md) VALUES (new.id, new.title, new.body_md);
END;

"""SQLite connection + sqlite-vec setup."""

import sqlite3
from pathlib import Path
import sqlite_vec

from . import DB_PATH, PROJECT_ROOT


SCHEMA_PATH = Path(__file__).parent / "schema.sql"
VEC_DIM = 3072  # text-embedding-3-large native dimension


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a connection with sqlite-vec loaded."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply the static schema."""
    sql = SCHEMA_PATH.read_text()
    conn.executescript(sql)
    conn.commit()


def init_vec_table(conn: sqlite3.Connection, dim: int = VEC_DIM) -> None:
    """Create the vec0 virtual table for vector search.

    Kept separate from the static schema because the dimension parameter
    is interpolated; CREATE VIRTUAL TABLE doesn't accept ? binding.
    """
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS embedding_vec USING vec0("
        f"  embedding_id INTEGER PRIMARY KEY,"
        f"  vector FLOAT[{dim}]"
        f")"
    )
    conn.commit()


def init(db_path: Path = DB_PATH, vec_dim: int = VEC_DIM) -> sqlite3.Connection:
    """Open + initialize schema + vec table. Idempotent."""
    conn = connect(db_path)
    init_schema(conn)
    init_vec_table(conn, vec_dim)
    return conn

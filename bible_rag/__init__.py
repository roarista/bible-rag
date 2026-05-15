"""Bible RAG — typology and meaning graph for scripture."""

from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "bible_rag.db"
VAULT_PATH = Path(
    "/Users/rodrigoarista/Library/Mobile Documents/com~apple~CloudDocs/"
    "Obsidian/Brain/01-Projects/Bible-RAG"
)

# Auto-load .env so OPENAI_API_KEY etc. are available without manual export.
load_dotenv(PROJECT_ROOT / ".env")

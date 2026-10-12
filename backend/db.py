"""SQLite connections and atomic, versioned bootstrap migration."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            try:
                tables = {row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )}
                if not tables:
                    # The fixed schema contains no triggers or semicolons inside strings.
                    # Avoid executescript: its implicit COMMIT would break atomic migration.
                    for statement in Path(__file__).with_name("schema.sql").read_text(encoding="utf-8").split(";"):
                        if statement.strip():
                            conn.execute(statement)
                    conn.execute("INSERT INTO schema_meta(version) VALUES (?)", (SCHEMA_VERSION,))
                else:
                    if "schema_meta" not in tables:
                        raise RuntimeError("Unversioned database; refusing destructive initialization")
                    versions = [row[0] for row in conn.execute("SELECT version FROM schema_meta")]
                    if versions != [SCHEMA_VERSION]:
                        raise RuntimeError(f"Unsupported schema version: {versions}")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

"""SQLite connections and atomic, versioned bootstrap migration."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from backend.migrations import MIGRATIONS, SCHEMA_VERSION


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

    @staticmethod
    def _version(conn):
        """None for an empty database; raises for anything we must not touch."""
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if not tables:
            return None
        if "schema_meta" not in tables:
            raise RuntimeError("Unversioned database; refusing destructive initialization")
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_meta")]
        if len(versions) != 1 or versions[0] not in range(1, SCHEMA_VERSION + 1):
            raise RuntimeError(f"Unsupported schema version: {versions}")
        return versions[0]

    def _backup(self, conn, version):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.path.with_name(f"{self.path.name}.bak-v{version}-{stamp}")
        destination = sqlite3.connect(target)
        try:
            conn.backup(destination)  # consistent even while WAL has uncheckpointed pages
        finally:
            destination.close()
        # Keep the three newest backups; migrations are rare, disks are not infinite.
        old = sorted(self.path.parent.glob(f"{self.path.name}.bak-v*"))[:-3]
        for path in old:
            path.unlink(missing_ok=True)

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            if self._version(conn) == SCHEMA_VERSION:
                return  # hot path: called on every resolve
            current = self._version(conn)
            if current is not None:
                self._backup(conn, current)
            conn.execute("BEGIN IMMEDIATE")
            try:
                current = self._version(conn)  # another process may have migrated meanwhile
                if current is None:
                    # The frozen baseline has no triggers or semicolons inside strings.
                    # Avoid executescript: its implicit COMMIT would break atomic migration.
                    for statement in Path(__file__).with_name("schema.sql").read_text(encoding="utf-8").split(";"):
                        if statement.strip():
                            conn.execute(statement)
                    conn.execute("INSERT INTO schema_meta(version) VALUES (1)")
                    current = 1
                for version in range(current + 1, SCHEMA_VERSION + 1):
                    for statement in MIGRATIONS[version]:
                        conn.execute(statement)
                    conn.execute("UPDATE schema_meta SET version=?", (version,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

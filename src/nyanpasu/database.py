from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@contextmanager
def database_connection(path: Path) -> Generator[sqlite3.Connection]:
    # A sqlite3.Connection context commits/rolls back, but does not close it.
    with closing(sqlite3.connect(path, timeout=30)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        with connection:
            yield connection

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from nyanpasu.config import NyanpasuConfig
from nyanpasu.database import database_connection
from nyanpasu.web import create_app


def test_database_transactions_close_connections_on_success_and_failure(tmp_path):
    path = tmp_path / "state.sqlite3"
    with database_connection(path) as connection:
        connection.execute("CREATE TABLE records (value TEXT)")
        connection.execute("INSERT INTO records VALUES ('committed')")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(ValueError, match="rollback"):
        with database_connection(path) as failed:
            failed.execute("INSERT INTO records VALUES ('rolled back')")
            raise ValueError("rollback")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed.execute("SELECT 1")
    with database_connection(path) as reopened:
        assert [row[0] for row in reopened.execute("SELECT value FROM records")] == ["committed"]
    path.unlink()


def test_real_app_starts_serves_dashboard_and_releases_database(tmp_path):
    config = NyanpasuConfig(state_dir=tmp_path)
    with TestClient(create_app(config)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/dashboard").status_code == 200
        assert client.get("/api/dashboard").status_code == 200
    config.db_path.unlink()

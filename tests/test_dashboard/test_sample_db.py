"""Tests for the sample finance database."""
import sqlite3

import pytest

from yigthinker.dashboard.sample_db import ensure_sample_db


@pytest.fixture
def sample_db(tmp_path, monkeypatch):
    db_path = tmp_path / "sample_finance.db"
    monkeypatch.setattr("yigthinker.dashboard.sample_db.SAMPLE_DB_PATH", db_path)
    return ensure_sample_db()


def test_sample_db_creates(sample_db):
    assert sample_db.exists()


def test_sample_db_has_revenue_table(sample_db):
    conn = sqlite3.connect(str(sample_db))
    cur = conn.execute("SELECT COUNT(*) FROM revenue")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 18  # 3 regions x 6 quarters (4 in 2025 + 2 in 2026)


def test_sample_db_has_accounts_payable(sample_db):
    conn = sqlite3.connect(str(sample_db))
    cur = conn.execute("SELECT COUNT(*) FROM accounts_payable")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 18


def test_sample_db_has_expenses(sample_db):
    conn = sqlite3.connect(str(sample_db))
    cur = conn.execute("SELECT COUNT(*) FROM expenses")
    count = cur.fetchone()[0]
    conn.close()
    # 5 categories x 4 departments x 15 months (12 in 2025 + 3 in 2026)
    assert count == 300


def test_sample_db_has_anomalies(sample_db):
    """AP data includes deliberate anomalies for demo queries."""
    conn = sqlite3.connect(str(sample_db))
    cur = conn.execute(
        "SELECT supplier, amount FROM accounts_payable WHERE amount > 100000 ORDER BY amount DESC"
    )
    rows = cur.fetchall()
    conn.close()
    # Shanghai Metals 187K spike, Acme Corp 125K spike, Shanghai Metals 112K (normal but large)
    assert len(rows) >= 2
    assert rows[0][0] == "Shanghai Metals"


def test_sample_db_idempotent(sample_db, tmp_path, monkeypatch):
    """Calling ensure_sample_db again returns the same path without error."""
    monkeypatch.setattr("yigthinker.dashboard.sample_db.SAMPLE_DB_PATH", sample_db)
    path2 = ensure_sample_db()
    assert path2 == sample_db

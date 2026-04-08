"""Sample SQLite finance database for guided first experience.

Creates a small but realistic finance dataset that demonstrates
Yigthinker's analysis capabilities within 60 seconds of first load.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SAMPLE_DB_PATH = Path.home() / ".yigthinker" / "sample_finance.db"


def ensure_sample_db() -> Path:
    """Create the sample finance DB if it doesn't exist. Returns the path."""
    if SAMPLE_DB_PATH.exists():
        return SAMPLE_DB_PATH

    SAMPLE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SAMPLE_DB_PATH))
    _populate(conn)
    conn.close()
    return SAMPLE_DB_PATH


def _populate(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Revenue by region and quarter
    cur.execute("""
        CREATE TABLE revenue (
            id INTEGER PRIMARY KEY,
            region TEXT NOT NULL,
            quarter TEXT NOT NULL,
            year INTEGER NOT NULL,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'EUR'
        )
    """)

    revenue_data = [
        # 2025
        ("EMEA", "Q1", 2025, 1_240_000), ("EMEA", "Q2", 2025, 1_380_000),
        ("EMEA", "Q3", 2025, 1_150_000), ("EMEA", "Q4", 2025, 1_520_000),
        ("APAC", "Q1", 2025, 890_000), ("APAC", "Q2", 2025, 1_020_000),
        ("APAC", "Q3", 2025, 950_000), ("APAC", "Q4", 2025, 1_180_000),
        ("Americas", "Q1", 2025, 2_100_000), ("Americas", "Q2", 2025, 2_340_000),
        ("Americas", "Q3", 2025, 1_980_000), ("Americas", "Q4", 2025, 2_510_000),
        # 2026
        ("EMEA", "Q1", 2026, 1_410_000), ("EMEA", "Q2", 2026, 1_560_000),
        ("APAC", "Q1", 2026, 1_050_000), ("APAC", "Q2", 2026, 1_190_000),
        ("Americas", "Q1", 2026, 2_280_000), ("Americas", "Q2", 2026, 2_590_000),
    ]
    cur.executemany(
        "INSERT INTO revenue (region, quarter, year, amount) VALUES (?, ?, ?, ?)",
        revenue_data,
    )

    # Accounts payable with some anomalies
    cur.execute("""
        CREATE TABLE accounts_payable (
            id INTEGER PRIMARY KEY,
            supplier TEXT NOT NULL,
            invoice_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            region TEXT NOT NULL
        )
    """)

    ap_data = [
        ("Acme Corp", "2026-01-15", "2026-02-15", 45_000, "paid", "EMEA"),
        ("Acme Corp", "2026-02-10", "2026-03-10", 48_200, "paid", "EMEA"),
        ("Acme Corp", "2026-03-05", "2026-04-05", 125_000, "pending", "EMEA"),  # anomaly: spike
        ("TechParts Ltd", "2026-01-20", "2026-02-20", 23_500, "paid", "APAC"),
        ("TechParts Ltd", "2026-02-18", "2026-03-18", 21_800, "paid", "APAC"),
        ("TechParts Ltd", "2026-03-12", "2026-04-12", 89_000, "overdue", "APAC"),  # anomaly
        ("GlobalShip Inc", "2026-01-08", "2026-02-08", 67_000, "paid", "Americas"),
        ("GlobalShip Inc", "2026-02-05", "2026-03-05", 71_200, "paid", "Americas"),
        ("GlobalShip Inc", "2026-03-01", "2026-04-01", 69_500, "pending", "Americas"),
        ("Shanghai Metals", "2026-01-25", "2026-02-25", 112_000, "paid", "APAC"),
        ("Shanghai Metals", "2026-02-20", "2026-03-20", 108_500, "paid", "APAC"),
        ("Shanghai Metals", "2026-03-15", "2026-04-15", 187_000, "pending", "APAC"),  # anomaly
        ("Berlin Logistics", "2026-01-12", "2026-02-12", 34_000, "paid", "EMEA"),
        ("Berlin Logistics", "2026-02-08", "2026-03-08", 36_200, "paid", "EMEA"),
        ("Berlin Logistics", "2026-03-03", "2026-04-03", 38_100, "pending", "EMEA"),
        ("MexiParts SA", "2026-01-18", "2026-02-18", 55_000, "paid", "Americas"),
        ("MexiParts SA", "2026-02-14", "2026-03-14", 52_800, "paid", "Americas"),
        ("MexiParts SA", "2026-03-10", "2026-04-10", 58_200, "pending", "Americas"),
    ]
    cur.executemany(
        "INSERT INTO accounts_payable (supplier, invoice_date, due_date, amount, status, region) VALUES (?, ?, ?, ?, ?, ?)",
        ap_data,
    )

    # Monthly expenses for forecasting
    cur.execute("""
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            month TEXT NOT NULL,
            amount REAL NOT NULL,
            department TEXT NOT NULL
        )
    """)

    categories = ["Payroll", "Cloud Infra", "Office", "Travel", "Marketing"]
    departments = ["Engineering", "Sales", "Operations", "Finance"]
    import random
    random.seed(42)

    for year in [2025, 2026]:
        months = range(1, 13) if year == 2025 else range(1, 4)
        for month in months:
            m = f"{year}-{month:02d}"
            for cat in categories:
                base = {"Payroll": 180_000, "Cloud Infra": 45_000, "Office": 22_000, "Travel": 15_000, "Marketing": 35_000}
                for dept in departments:
                    amount = base[cat] * (0.8 + random.random() * 0.4) / len(departments)
                    cur.execute(
                        "INSERT INTO expenses (category, month, amount, department) VALUES (?, ?, ?, ?)",
                        (cat, m, round(amount, 2), dept),
                    )

    conn.commit()

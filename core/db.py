import hashlib
import sqlite3
import uuid
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "expenses.db"


def conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS expenses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            payment_method TEXT,
            source TEXT DEFAULT 'manual',
            hash TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS budgets(category TEXT PRIMARY KEY, amount REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        """)


def make_hash(date, amount, description, seq=0):
    raw = f"{date}|{round(float(amount), 2)}|{description.lower().strip()}|{seq}"
    return hashlib.sha1(raw.encode()).hexdigest()


def insert_many(rows, manual=False):
    """rows: dicts with date(YYYY-MM-DD), description, amount, category,
    payment_method, optional seq. Returns (added, skipped_duplicates)."""
    added = 0
    with conn() as c:
        for r in rows:
            h = uuid.uuid4().hex if manual else make_hash(
                r["date"], r["amount"], r["description"], r.get("seq", 0))
            cur = c.execute(
                "INSERT OR IGNORE INTO expenses(date,description,amount,category,payment_method,source,hash) "
                "VALUES(?,?,?,?,?,?,?)",
                (r["date"], r["description"], float(r["amount"]), r["category"],
                 r.get("payment_method", "Other"), "manual" if manual else "import", h))
            added += cur.rowcount
    return added, len(rows) - added


def update_expense(id_, date, description, amount, category, payment_method):
    with conn() as c:
        c.execute("UPDATE expenses SET date=?,description=?,amount=?,category=?,payment_method=? WHERE id=?",
                  (str(date), description, float(amount), category, payment_method, int(id_)))


def delete_expense(id_):
    with conn() as c:
        c.execute("DELETE FROM expenses WHERE id=?", (int(id_),))


def load_df():
    with conn() as c:
        df = pd.read_sql("SELECT id,date,description,amount,category,payment_method,source "
                         "FROM expenses ORDER BY date DESC, id DESC", c)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.strftime("%Y-%m")
    return df


def get_budgets():
    with conn() as c:
        return dict(c.execute("SELECT category, amount FROM budgets").fetchall())


def set_budgets(budgets: dict):
    with conn() as c:
        c.execute("DELETE FROM budgets")
        c.executemany("INSERT INTO budgets VALUES(?,?)",
                      [(k, float(v)) for k, v in budgets.items() if float(v) > 0])


def get_income():
    with conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key='income'").fetchone()
    return float(row[0]) if row else 0.0


def set_income(value):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES('income', ?)", (str(float(value)),))

from __future__ import annotations

import sqlite3
from pathlib import Path

from itau_ri_sanitize.paths import pipeline_dir


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    sha256 TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    n_pages INTEGER,
    family TEXT,
    status TEXT NOT NULL,
    error TEXT,
    staging_path TEXT,
    n_remove INTEGER DEFAULT 0,
    n_review INTEGER DEFAULT 0,
    n_keep INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS paths (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    sha256 TEXT NOT NULL,
    page_index INTEGER NOT NULL,
    n_chars INTEGER,
    action TEXT NOT NULL,
    reasons TEXT NOT NULL,
    PRIMARY KEY (sha256, page_index)
);
"""


def connect() -> sqlite3.Connection:
    path = pipeline_dir() / "work" / "manifest.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

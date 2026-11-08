# -*- coding: utf-8 -*-
"""
Database Connection Manager.
Supports both PostgreSQL (production) and SQLite (offline/local fallback).
Handles thread-safe connections and standardizes SQL parameter syntax (%s vs ?).
"""

import sqlite3
import os
from contextlib import contextmanager
from typing import Generator, Any, Tuple
from neev_backend.config.settings import settings

try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

class DatabaseConnectionManager:
    """Manages connection lifecycles, pooling, and schema initialization."""

    def __init__(self, db_url: str = None, sqlite_path: str = None):
        self.db_url = db_url or settings.DATABASE_URL
        self.sqlite_path = sqlite_path or str(settings.SQLITE_PATH)
        self.is_postgres = bool(self.db_url and PSYCOPG2_AVAILABLE)
        self._init_schema()

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Provides a managed connection context with automatic commit/rollback."""
        if self.is_postgres:
            conn = psycopg2.connect(self.db_url)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def format_query(self, query: str) -> str:
        """Adapts SQL parameter placeholders: PostgreSQL (%s) vs SQLite (?)."""
        if self.is_postgres:
            return query.replace("?", "%s")
        return query

    def _init_schema(self):
        """Initializes tables and indices for users, student profiles, and chat logs."""
        schema_users = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(64) PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        schema_profiles = """
        CREATE TABLE IF NOT EXISTS student_profiles (
            user_id VARCHAR(64) PRIMARY KEY,
            profile_data TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
        schema_chat = """
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id VARCHAR(64) NOT NULL,
            role VARCHAR(32) NOT NULL,
            content TEXT NOT NULL,
            status VARCHAR(64),
            matched_college TEXT,
            evidence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        if self.is_postgres:
            schema_chat = schema_chat.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")

        idx_chat = "CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history (user_id, created_at DESC);"

        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(schema_users)
            cur.execute(schema_profiles)
            cur.execute(schema_chat)
            cur.execute(idx_chat)
            cur.close()

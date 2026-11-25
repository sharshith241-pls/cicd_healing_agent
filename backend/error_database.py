"""
CICD Error Memory
SQLite backend for storing errors, successful fixes, logs and similarities.
"""

import json
import logging
import sqlite3
import zlib
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorDatabase:
    """
    SQLite-based failure memory for the self-healing CI/CD system.

    Stores:
    - Previous errors
    - Successful fixes
    - Fix success rates
    - Compressed logs
    - Error similarity relationships
    """

    def __init__(
        self,
        db_url: str = "sqlite:///./workspace/cicd_errors.db",
    ):
        self.db_url = db_url
        self.conn: Optional[sqlite3.Connection] = None

        self.connect()
        self.init_schema()

    # ------------------------------------------------------------------
    # DATABASE CONNECTION
    # ------------------------------------------------------------------

    def _resolve_database_path(self) -> str:
        """Convert SQLite URL into a usable local file path."""

        if not self.db_url:
            return "cicd_errors.db"

        if self.db_url == ":memory:":
            return ":memory:"

        if self.db_url.startswith("sqlite:///"):
            path = self.db_url[len("sqlite:///"):]

            if not Path(path).is_absolute():
                path = Path.cwd() / path

            path = Path(path)

        else:
            path = Path(self.db_url)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        return str(path)

    def connect(self):
        """Open SQLite database connection."""

        try:
            database_path = self._resolve_database_path()

            self.conn = sqlite3.connect(
                database_path,
                check_same_thread=False,
            )

            self.conn.row_factory = sqlite3.Row

            logger.info(
                "Connected to SQLite database: %s",
                database_path,
            )

        except sqlite3.Error as exc:
            logger.error(
                "Failed to connect to SQLite database: %s",
                exc,
            )
            raise

    # ------------------------------------------------------------------
    # SCHEMA
    # ------------------------------------------------------------------

    def init_schema(self):
        """Create all required tables and indexes."""

        if not self.conn:
            raise RuntimeError(
                "Database connection is not available."
            )

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_hash TEXT UNIQUE NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    repo_url TEXT,
                    file_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    occurrence_count INTEGER DEFAULT 1,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    severity TEXT DEFAULT 'medium'
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fixes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_id INTEGER NOT NULL,
                    fix_description TEXT,
                    fixed_code TEXT,
                    fix_method TEXT,
                    source TEXT,
                    applied_count INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ai_model TEXT,
                    FOREIGN KEY (error_id)
                        REFERENCES errors(id)
                        ON DELETE CASCADE
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_id INTEGER NOT NULL,
                    fix_id INTEGER,
                    log_content BLOB NOT NULL,
                    log_summary TEXT,
                    log_size INTEGER,
                    original_size INTEGER,
                    compression_ratio REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (error_id)
                        REFERENCES errors(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (fix_id)
                        REFERENCES fixes(id)
                        ON DELETE SET NULL
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS error_similarities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_id_1 INTEGER NOT NULL,
                    error_id_2 INTEGER NOT NULL,
                    similarity_score REAL,
                    match_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (error_id_1)
                        REFERENCES errors(id)
                        ON DELETE CASCADE,
                    FOREIGN KEY (error_id_2)
                        REFERENCES errors(id)
                        ON DELETE CASCADE,
                    UNIQUE(error_id_1, error_id_2)
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_hash
                ON errors(error_hash)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_type
                ON errors(error_type)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_repo_url
                ON errors(repo_url)
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON errors(created_at)
                """
            )

            self.conn.commit()

            logger.info(
                "SQLite error-memory schema initialized."
            )

        except sqlite3.Error as exc:
            self.conn.rollback()

            logger.error(
                "Failed to initialize database schema: %s",
                exc,
            )

            raise

    # ------------------------------------------------------------------
    # ERROR MEMORY
    # ------------------------------------------------------------------

    def store_error(
        self,
        error_hash: str,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        repo_url: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> int:
        """Store a new error or increment an existing error."""

        if not self.conn:
            raise RuntimeError(
                "Database connection is not available."
            )

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT id
                FROM errors
                WHERE error_hash = ?
                """,
                (error_hash,),
            )

            existing = cursor.fetchone()

            if existing:

                error_id = existing["id"]

                cursor.execute(
                    """
                    UPDATE errors
                    SET occurrence_count =
                            occurrence_count + 1,
                        last_seen =
                            CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (error_id,),
                )

            else:

                cursor.execute(
                    """
                    INSERT INTO errors (
                        error_hash,
                        error_type,
                        error_message,
                        stack_trace,
                        repo_url,
                        file_path
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        error_hash,
                        error_type,
                        error_message,
                        stack_trace,
                        repo_url,
                        file_path,
                    ),
                )

                error_id = cursor.lastrowid

            self.conn.commit()

            return int(error_id)

        except sqlite3.Error as exc:

            self.conn.rollback()

            logger.error(
                "Failed to store error: %s",
                exc,
            )

            raise

    def get_error_by_hash(
        self,
        error_hash: str,
    ) -> Optional[dict]:
        """Retrieve a previously seen error."""

        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT *
                FROM errors
                WHERE error_hash = ?
                """,
                (error_hash,),
            )

            row = cursor.fetchone()

            return dict(row) if row else None

        except sqlite3.Error as exc:

            logger.error(
                "Failed to retrieve error: %s",
                exc,
            )

            return None

    # ------------------------------------------------------------------
    # SIMILAR ERRORS
    # ------------------------------------------------------------------

    def get_similar_errors(
        self,
        error_id: int,
        limit: int = 5,
    ) -> list[dict]:
        """Retrieve similar previously recorded errors."""

        if not self.conn:
            return []

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT
                    e.*,
                    s.similarity_score,
                    s.match_type
                FROM error_similarities s
                JOIN errors e
                    ON (
                        (
                            s.error_id_1 = e.id
                            AND s.error_id_2 = ?
                        )
                        OR
                        (
                            s.error_id_2 = e.id
                            AND s.error_id_1 = ?
                        )
                    )
                WHERE s.similarity_score > 0.7
                ORDER BY s.similarity_score DESC
                LIMIT ?
                """,
                (
                    error_id,
                    error_id,
                    limit,
                ),
            )

            return [
                dict(row)
                for row in cursor.fetchall()
            ]

        except sqlite3.Error as exc:

            logger.error(
                "Failed to retrieve similar errors: %s",
                exc,
            )

            return []

    # ------------------------------------------------------------------
    # FIX MEMORY
    # ------------------------------------------------------------------

    def get_fix_for_error(
        self,
        error_id: int,
    ) -> Optional[dict]:
        """
        Retrieve a reliable known fix.

        A fix is eligible for automatic reuse only when:

        1. It has been successfully applied at least once.
        2. Its recorded success rate is at least 90%.
        3. It has at least one recorded application.

        The highest-confidence eligible fix is returned.

        This prevents an untested or failed candidate from being
        treated as trusted memory.
        """

        fixes = self.get_fixes_for_error(error_id)
        for fix in fixes:
            try:
                changes = json.loads(fix["fixed_code"])
            except (TypeError, json.JSONDecodeError):
                continue

            if (
                isinstance(changes, dict)
                and changes
                and all(
                    isinstance(path, str) and isinstance(code, str)
                    for path, code in changes.items()
                )
            ):
                return fix

        return fixes[0] if fixes else None

    def get_fixes_for_error(
        self,
        error_id: int,
    ) -> list[dict]:
        """Return all trusted fixes, ordered from most to least successful."""

        if not self.conn:
            return []

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM fixes
                WHERE error_id = ?
                  AND applied_count >= 1
                  AND success_rate >= 0.90
                ORDER BY success_rate DESC,
                         applied_count DESC,
                         created_at DESC,
                         id DESC
                """,
                (error_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

        except sqlite3.Error as exc:
            logger.error("Failed to retrieve fixes: %s", exc)
            return []

    def store_fix(
        self,
        error_id: int,
        fix_description: str,
        fixed_code: str,
        fix_method: str = "ai",
        source: str = "cache",
        ai_model: Optional[str] = None,
    ) -> int:
        """Store a newly generated fix."""

        if not self.conn:
            raise RuntimeError(
                "Database connection is not available."
            )

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                INSERT INTO fixes (
                    error_id,
                    fix_description,
                    fixed_code,
                    fix_method,
                    source,
                    ai_model
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    error_id,
                    fix_description,
                    fixed_code,
                    fix_method,
                    source,
                    ai_model,
                ),
            )

            fix_id = cursor.lastrowid

            self.conn.commit()

            return int(fix_id)

        except sqlite3.Error as exc:

            self.conn.rollback()

            logger.error(
                "Failed to store fix: %s",
                exc,
            )

            raise

    def update_fix_success(
        self,
        fix_id: int,
        success: bool,
    ) -> bool:
        """Update the observed success rate of a fix."""

        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT applied_count,
                       success_rate
                FROM fixes
                WHERE id = ?
                """,
                (fix_id,),
            )

            row = cursor.fetchone()

            if not row:
                return False

            old_count = int(
                row["applied_count"] or 0
            )

            old_rate = float(
                row["success_rate"] or 0.0
            )

            new_count = old_count + 1

            successful_attempts = (
                old_rate * old_count
            ) + (
                1 if success else 0
            )

            new_rate = (
                successful_attempts / new_count
            )

            cursor.execute(
                """
                UPDATE fixes
                SET applied_count = ?,
                    success_rate = ?
                WHERE id = ?
                """,
                (
                    new_count,
                    new_rate,
                    fix_id,
                ),
            )

            self.conn.commit()

            return True

        except sqlite3.Error as exc:

            self.conn.rollback()

            logger.error(
                "Failed to update fix success: %s",
                exc,
            )

            return False

    # ------------------------------------------------------------------
    # LOG STORAGE
    # ------------------------------------------------------------------

    def store_log(
        self,
        error_id: int,
        log_content: str,
        fix_id: Optional[int] = None,
        log_summary: Optional[str] = None,
    ) -> int:
        """Store compressed execution logs."""

        if not self.conn:
            raise RuntimeError(
                "Database connection is not available."
            )

        try:
            raw_bytes = log_content.encode(
                "utf-8"
            )

            compressed = zlib.compress(
                raw_bytes
            )

            original_size = len(
                raw_bytes
            )

            compressed_size = len(
                compressed
            )

            if original_size > 0:
                compression_ratio = (
                    compressed_size
                    / original_size
                )
            else:
                compression_ratio = 0.0

            cursor = self.conn.cursor()

            cursor.execute(
                """
                INSERT INTO logs (
                    error_id,
                    fix_id,
                    log_content,
                    log_summary,
                    log_size,
                    original_size,
                    compression_ratio
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    error_id,
                    fix_id,
                    compressed,
                    log_summary,
                    compressed_size,
                    original_size,
                    compression_ratio,
                ),
            )

            log_id = cursor.lastrowid

            self.conn.commit()

            return int(log_id)

        except sqlite3.Error as exc:

            self.conn.rollback()

            logger.error(
                "Failed to store log: %s",
                exc,
            )

            raise

    # ------------------------------------------------------------------
    # ERROR SIMILARITY
    # ------------------------------------------------------------------

    def store_error_similarity(
        self,
        error_id_1: int,
        error_id_2: int,
        similarity_score: float,
        match_type: str,
    ) -> bool:
        """Store or update error similarity."""

        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                INSERT INTO error_similarities (
                    error_id_1,
                    error_id_2,
                    similarity_score,
                    match_type
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(error_id_1, error_id_2)
                DO UPDATE SET
                    similarity_score =
                        excluded.similarity_score,
                    match_type =
                        excluded.match_type
                """,
                (
                    error_id_1,
                    error_id_2,
                    similarity_score,
                    match_type,
                ),
            )

            self.conn.commit()

            return True

        except sqlite3.Error as exc:

            self.conn.rollback()

            logger.error(
                "Failed to store error similarity: %s",
                exc,
            )

            return False

    # ------------------------------------------------------------------
    # STATISTICS
    # ------------------------------------------------------------------

    def get_error_statistics(self) -> dict:
        """Return dashboard-friendly memory statistics."""

        if not self.conn:
            return {}

        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_errors,
                    COUNT(DISTINCT error_type)
                        AS unique_error_types,
                    COALESCE(
                        SUM(occurrence_count),
                        0
                    ) AS total_occurrences,
                    COALESCE(
                        AVG(occurrence_count),
                        0
                    ) AS avg_occurrences
                FROM errors
                """
            )

            error_stats = dict(
                cursor.fetchone()
            )

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_fixes,
                    COALESCE(
                        AVG(success_rate),
                        0
                    ) AS avg_success_rate
                FROM fixes
                """
            )

            fix_stats = dict(
                cursor.fetchone()
            )

            return {
                **error_stats,
                **fix_stats,
            }

        except sqlite3.Error as exc:

            logger.error(
                "Failed to get statistics: %s",
                exc,
            )

            return {}

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------

    def close(self):
        """Close database connection."""

        if self.conn:

            self.conn.close()
            self.conn = None

            logger.info(
                "SQLite database connection closed."
            )
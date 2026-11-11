"""SQLite cache and token ledger; never stores credentials or API responses."""

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .vocabulary import Vocabulary, normalize

logger = logging.getLogger(__name__)

USAGE_QUERY = (
    "SELECT model, COUNT(*) AS requests, SUM(prompt_tokens) AS prompt_tokens, "
    "SUM(completion_tokens) AS completion_tokens, "
    "SUM(total_tokens) AS total_tokens, "
    "SUM(cached_tokens) AS cached_tokens FROM usage GROUP BY model"
)


def usage_rows(db: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = db.execute(USAGE_QUERY)
    return [dict(zip([d[0] for d in cursor.description], row)) for row in cursor]


class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                word TEXT NOT NULL, topic TEXT NOT NULL, context TEXT NOT NULL,
                content TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (word, topic, context)
            );
            CREATE TABLE IF NOT EXISTS usage (
                id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                model TEXT NOT NULL, prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL,
                cached_tokens INTEGER NOT NULL
            );
        """)
        self.db.commit()

    def __enter__(self) -> "Cache":
        return self

    def __exit__(self, *_: Any) -> None:
        self.db.close()

    def get(self, word: str, topic: str, context: str = "") -> Vocabulary | None:
        row = self.db.execute(
            "SELECT content FROM vocabulary WHERE word=? AND topic=? AND context=?",
            (normalize(word), normalize(topic), context),
        ).fetchone()
        if not row:
            return None
        try:
            return Vocabulary.from_dict(json.loads(row[0]))
        except (ValueError, ValidationError):
            logger.warning("忽略一条无法解析的旧缓存，准备重新生成。")
            return None

    def put(self, entry: Vocabulary) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO vocabulary(word, topic, context, content) VALUES(?,?,?,?) "
                "ON CONFLICT(word, topic, context) DO UPDATE SET "
                "content=excluded.content, updated_at=CURRENT_TIMESTAMP",
                (
                    normalize(entry.word),
                    normalize(entry.topic),
                    entry.source_sentence,
                    json.dumps(entry.to_dict(), ensure_ascii=False),
                ),
            )

    def record_usage(
        self,
        model: str,
        prompt: int,
        completion: int,
        total: int,
        cached: int = 0,
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO usage(model, prompt_tokens, completion_tokens, "
                "total_tokens, cached_tokens) VALUES(?,?,?,?,?)",
                (model, prompt, completion, total, cached),
            )

    def usage(self) -> list[dict[str, Any]]:
        return usage_rows(self.db)

    @staticmethod
    def read_usage(path: Path) -> list[dict[str, Any]]:
        """Read the ledger without creating or modifying a database."""
        if not path.is_file():
            return []
        with closing(
            sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=1,
            )
        ) as db:
            return usage_rows(db)

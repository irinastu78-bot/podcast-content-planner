"""
services/db_service.py
Постоянное хранение данных в SQLite.
Таблицы: users (пользователи), materials (источники), projects (подкасты).
На первом этапе используются функции для users; таблицы materials и
projects создаются заранее, наполним их функциями на следующем этапе.
"""

from __future__ import annotations
import os
import sqlite3
import json
from datetime import datetime, timezone
import hashlib

# Файл базы лежит в корне проекта. Данные сохраняются между сессиями.
DB_PATH = os.getenv("DB_PATH", "podcast_planner.db")


def _connect() -> sqlite3.Connection:
    """Открывает соединение с включённой поддержкой внешних ключей."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # доступ к колонкам по имени
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Вызывается при старте приложения."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS materials (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                source_type TEXT NOT NULL,          -- 'file' или 'url'
                name        TEXT NOT NULL,          -- имя файла или URL
                fingerprint TEXT NOT NULL,          -- отпечаток содержимого
                content     TEXT NOT NULL,          -- извлечённый текст
                created_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                title       TEXT NOT NULL,          -- название проекта
                data        TEXT NOT NULL,          -- весь проект в JSON
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Работа с пользователями ---

def create_user(username: str, password_hash: str) -> int:
    """
    Создаёт пользователя. Возвращает его id.
    Бросает ValueError, если логин уже занят.
    """
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, created_at) "
                "VALUES (?, ?, ?)",
                (username, password_hash, _now()),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Пользователь с таким логином уже существует.")


def get_user(username: str) -> dict | None:
    """Возвращает пользователя по логину или None, если не найден."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, created_at "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return dict(row) if row else None


def user_count() -> int:
    """Сколько всего пользователей (пригодится для подсказок в интерфейсе)."""
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def fingerprint(text: str) -> str:
    """Отпечаток содержимого — для защиты от случайных дублей материала."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# --- Работа с материалами (источниками) ---

def add_material(user_id: int, source_type: str, name: str, content: str) -> int:
    """
    Сохраняет материал пользователя. Если такой же по содержимому материал
    у пользователя уже есть — возвращает id существующего, не создавая дубль.
    """
    fp = fingerprint(content)
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM materials WHERE user_id = ? AND fingerprint = ?",
            (user_id, fp),
        ).fetchone()
        if existing:
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO materials (user_id, source_type, name, fingerprint, "
            "content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, source_type, name, fp, content, _now()),
        )
        return cur.lastrowid


def list_materials(user_id: int) -> list[dict]:
    """Все материалы пользователя, новые сверху."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, source_type, name, content, created_at "
            "FROM materials WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_materials_by_ids(user_id: int, ids: list[int]) -> list[dict]:
    """Материалы по списку id (только принадлежащие пользователю)."""
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, name, content FROM materials "
            f"WHERE user_id = ? AND id IN ({placeholders})",
            (user_id, *ids),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_material(user_id: int, material_id: int) -> None:
    """Удаляет материал пользователя."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM materials WHERE user_id = ? AND id = ?",
            (user_id, material_id),
        )


# --- Работа с проектами (подкастами) ---

def save_project(user_id: int, title: str, data: dict) -> int:
    """Создаёт новый проект. data — весь проект (параметры, идеи, план и т.д.)."""
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO projects (user_id, title, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, title, json.dumps(data, ensure_ascii=False), now, now),
        )
        return cur.lastrowid


def update_project(user_id: int, project_id: int, title: str, data: dict) -> None:
    """Обновляет существующий проект."""
    with _connect() as conn:
        conn.execute(
            "UPDATE projects SET title = ?, data = ?, updated_at = ? "
            "WHERE user_id = ? AND id = ?",
            (title, json.dumps(data, ensure_ascii=False), _now(),
             user_id, project_id),
        )


def list_projects(user_id: int) -> list[dict]:
    """Список проектов пользователя (без тяжёлого поля data), новые сверху."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at "
            "FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_project(user_id: int, project_id: int) -> dict | None:
    """Полный проект с распакованным data."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, data, created_at, updated_at "
            "FROM projects WHERE user_id = ? AND id = ?",
            (user_id, project_id),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["data"] = json.loads(result["data"])
    return result


def delete_project(user_id: int, project_id: int) -> None:
    """Удаляет проект пользователя."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM projects WHERE user_id = ? AND id = ?",
            (user_id, project_id),
        )

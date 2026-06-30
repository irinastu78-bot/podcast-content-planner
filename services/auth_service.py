"""
services/auth_service.py
Регистрация и вход пользователей.
Пароли хранятся ТОЛЬКО в виде bcrypt-хэша (с солью внутри хэша).
Открытый пароль нигде не сохраняется.
"""

from __future__ import annotations
import bcrypt

from services import db_service

# Минимальные требования к учётным данным.
MIN_USERNAME_LEN = 3
MIN_PASSWORD_LEN = 6


def _hash_password(password: str) -> str:
    """Создаёт bcrypt-хэш пароля. Соль генерируется автоматически."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Сравнивает введённый пароль с сохранённым хэшем."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except ValueError:
        return False


def register(username: str, password: str) -> dict:
    """
    Регистрирует нового пользователя.
    Возвращает словарь с id и username при успехе.
    Бросает ValueError с понятным сообщением при проблеме.
    """
    username = (username or "").strip()
    if len(username) < MIN_USERNAME_LEN:
        raise ValueError(f"Логин должен быть не короче {MIN_USERNAME_LEN} символов.")
    if len(password or "") < MIN_PASSWORD_LEN:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LEN} символов.")

    user_id = db_service.create_user(username, _hash_password(password))
    return {"id": user_id, "username": username}


def login(username: str, password: str) -> dict:
    """
    Проверяет логин и пароль.
    Возвращает словарь с id и username при успехе.
    Бросает ValueError при неверных данных.
    """
    username = (username or "").strip()
    user = db_service.get_user(username)
    if not user or not _verify_password(password, user["password_hash"]):
        # Намеренно одинаковая ошибка, чтобы не подсказывать,
        # существует логин или нет.
        raise ValueError("Неверный логин или пароль.")
    return {"id": user["id"], "username": user["username"]}

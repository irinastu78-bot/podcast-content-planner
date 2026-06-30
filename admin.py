"""admin.py — административные операции с базой. Запускать вручную."""
import sys
from services import db_service, auth_service


def list_users():
    """Показать всех пользователей."""
    with db_service._connect() as conn:
        rows = conn.execute(
            "SELECT id, username, created_at FROM users ORDER BY id"
        ).fetchall()
    for r in rows:
        print(f"id={r['id']:>3}  {r['username']:<20}  создан: {r['created_at']}")
    if not rows:
        print("Пользователей нет.")


def delete_user(username):
    """Удалить пользователя и все его данные (материалы и проекты тоже)."""
    with db_service._connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        if cur.rowcount:
            print(f"Пользователь '{username}' и все его данные удалены.")
        else:
            print(f"Пользователь '{username}' не найден.")


def reset_password(username, new_password):
    """Сбросить пароль пользователю на новый (доступ к данным сохраняется)."""
    user = db_service.get_user(username)
    if not user:
        print(f"Пользователь '{username}' не найден.")
        return
    new_hash = auth_service._hash_password(new_password)
    with db_service._connect() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
    print(f"Пароль для '{username}' изменён. Новый пароль: {new_password}")


if __name__ == "__main__":
    db_service.init_db()
    if len(sys.argv) < 2:
        print("Команды:")
        print("  python admin.py list")
        print("  python admin.py delete <логин>")
        print("  python admin.py reset <логин> <новый_пароль>")
    elif sys.argv[1] == "list":
        list_users()
    elif sys.argv[1] == "delete":
        delete_user(sys.argv[2])
    elif sys.argv[1] == "reset":
        reset_password(sys.argv[2], sys.argv[3])
    else:
        print(f"Неизвестная команда: {sys.argv[1]}")

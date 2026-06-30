"""
services/llm_service.py
Обёртка над OpenAI API.
- Один клиент на всё приложение.
- Системная роль продюсера из prompts.SYSTEM_PROMPT.
- Запрос ответа строго в JSON и его разбор.
"""

from __future__ import annotations
import os
import json
from openai import OpenAI

from core.prompts import SYSTEM_PROMPT

# --- Проброс секретов из st.secrets в переменные окружения ---
# Локально ключи берутся из .env (python-dotenv), в Streamlit Cloud — из st.secrets.
# Этот блок должен выполниться ДО создания клиента OpenAI ниже.
try:
    import streamlit as st
    for _key in ("OPENAI_API_KEY", "OPENAI_MODEL", "DB_PATH"):
        try:
            if _key in st.secrets and not os.getenv(_key):
                os.environ[_key] = str(st.secrets[_key])
        except Exception:
            pass  # st.secrets может бросать, если файла секретов нет
except Exception:
    pass  # локально streamlit-секреты могут отсутствовать — берём из .env
# --------------------------------------------------------------

# Модель по умолчанию. gpt-4o-mini — дёшево и качественно для текста.
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Клиент берёт ключ из переменной окружения OPENAI_API_KEY.
_client = OpenAI()

def generate_json(
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.8,
) -> dict:
    """
    Отправляет промпт в модель и возвращает разобранный JSON (dict).
    Роль продюсера добавляется автоматически как system-сообщение.
    """
    try:
        response = _client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        raise RuntimeError(f"Ошибка обращения к OpenAI API: {e}") from e

    content = response.choices[0].message.content
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Модель вернула некорректный JSON: {e}\nОтвет: {content[:500]}"
        ) from e

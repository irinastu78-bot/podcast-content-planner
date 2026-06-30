"""check_call.py — проверяет реальный вызов выбранной модели с JSON-ответом."""
import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()
model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

print(f"Тестирую модель: {model}")

try:
    resp = client.chat.completions.create(
        model=model,
        temperature=0.8,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "Ты возвращаешь только валидный JSON."},
            {"role": "user", "content": 'Верни JSON вида {"ping": "pong", "n": 3}'},
        ],
    )
    content = resp.choices[0].message.content
    print("Сырой ответ:", content)
    print("Разобранный JSON:", json.loads(content))
    print("\n✅ Всё работает, можно запускать приложение.")
except Exception as e:
    print(f"\n❌ Ошибка: {type(e).__name__}: {e}")

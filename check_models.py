"""check_models.py — показывает модели, доступные твоему API-ключу."""
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

models = sorted(m.id for m in client.models.list().data)
for m in models:
    print(m)

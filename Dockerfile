FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Бот: python -m bot.main | Воркер: celery -A worker.celery_app:celery_app worker
CMD ["python", "-m", "bot.main"]

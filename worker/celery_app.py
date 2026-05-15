import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

_broker = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
_result = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

celery_app = Celery(
    "dating_bot",
    broker=_broker,
    backend=_result,
    include=["worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

_recalc_sec = float(os.getenv("CELERY_BEAT_RECALC_SEC", "3600"))

celery_app.conf.beat_schedule = {
    "recalculate-all-ratings": {
        "task": "worker.tasks.recalculate_all_ratings",
        "schedule": _recalc_sec,
    },
}

# Удобный алиас для CLI: `celery -A worker.celery_app worker`
app = celery_app

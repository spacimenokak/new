"""Запуск только /health и /metrics (без Telegram). Для проверки Prometheus-эндпоинтов."""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from metrics.http_server import start_metrics_server


async def main() -> None:
    port = int(os.getenv("METRICS_PORT", "9100"))
    await start_metrics_server(port)
    print(f"Метрики: http://localhost:{port}/metrics", flush=True)
    print(f"Health:  http://localhost:{port}/health", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

"""HTTP /metrics и /health для Prometheus и JMeter."""

from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

logger = logging.getLogger(__name__)


async def metrics_handler(_request: web.Request) -> web.Response:
    # CONTENT_TYPE_LATEST содержит charset= — его нельзя передавать в content_type= (aiohttp 3.9+).
    return web.Response(
        body=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )


async def health_handler(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "dating-bot"})


async def start_metrics_server(port: int | None = None) -> web.AppRunner:
    p = port or int(os.getenv("METRICS_PORT", "9100"))
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", p)
    await site.start()
    logger.info("Metrics server listening on 0.0.0.0:%s", p)
    return runner

"""
Unified load generator: same request mix and duration for every strategy endpoint.
Run: python load_generator.py --url http://127.0.0.1:8001 --read-ratio 0.8 --duration 30

Optional cache locality: --focus-pool 800 --focus-share 0.9 (90% of keys from 0..799).
Optional warmup: --warmup-seconds 10 then POST /admin/reset-counters before the timed phase.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from dataclasses import asdict, dataclass

import httpx


@dataclass
class LoadResult:
    label: str
    base_url: str
    read_ratio: float
    duration_s: float
    concurrency: int
    key_space: int
    seed_rows: int
    warmup_seconds: float
    focus_pool: int
    focus_share: float
    total_requests: int
    errors: int
    throughput_rps: float
    avg_latency_ms: float
    p95_latency_ms: float
    metrics_after: dict


def _pick_key(key_space: int, focus_pool: int, focus_share: float) -> str:
    if focus_pool > 0 and focus_share > 0 and random.random() < focus_share:
        bound = max(1, min(focus_pool, key_space))
        return str(random.randrange(bound))
    return str(random.randrange(key_space))


async def _worker(
    client: httpx.AsyncClient,
    base: str,
    read_ratio: float,
    key_space: int,
    focus_pool: int,
    focus_share: float,
    stop_at: float,
    latencies: list[float] | None,
    counters: dict,
) -> None:
    base = base.rstrip("/")
    while time.perf_counter() < stop_at:
        is_read = random.random() < read_ratio
        key = _pick_key(key_space, focus_pool, focus_share)
        t0 = time.perf_counter()
        try:
            if is_read:
                r = await client.get(f"{base}/items/{key}", timeout=30.0)
                if r.status_code == 404:
                    counters["errors"] += 1
                elif r.status_code != 200:
                    counters["errors"] += 1
            else:
                body = {"value": f"w-{key}-{random.randint(0, 10**9)}"}
                r = await client.put(f"{base}/items/{key}", json=body, timeout=30.0)
                if r.status_code != 200:
                    counters["errors"] += 1
        except httpx.HTTPError:
            counters["errors"] += 1
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if latencies is not None:
            latencies.append(dt_ms)
        counters["total"] += 1


async def _run_phase(
    client: httpx.AsyncClient,
    base_url: str,
    read_ratio: float,
    duration_s: float,
    concurrency: int,
    key_space: int,
    focus_pool: int,
    focus_share: float,
    latencies: list[float] | None,
    counters: dict,
) -> None:
    stop_at = time.perf_counter() + duration_s
    tasks = [
        asyncio.create_task(
            _worker(
                client,
                base_url,
                read_ratio,
                key_space,
                focus_pool,
                focus_share,
                stop_at,
                latencies,
                counters,
            )
        )
        for _ in range(concurrency)
    ]
    await asyncio.gather(*tasks)


async def run_load(
    base_url: str,
    read_ratio: float,
    duration_s: float,
    concurrency: int,
    key_space: int,
    seed_rows: int,
    label: str,
    warmup_seconds: float = 0.0,
    focus_pool: int = 0,
    focus_share: float = 0.85,
) -> LoadResult:
    base_url = base_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{base_url}/admin/reset",
            json={"seed_rows": seed_rows},
            timeout=120.0,
        )
        r.raise_for_status()

        if warmup_seconds > 0:
            wc: dict = {"total": 0, "errors": 0}
            await _run_phase(
                client,
                base_url,
                read_ratio,
                warmup_seconds,
                concurrency,
                key_space,
                focus_pool,
                focus_share,
                None,
                wc,
            )
            rc = await client.post(f"{base_url}/admin/reset-counters", timeout=30.0)
            rc.raise_for_status()

        latencies: list[float] = []
        counters = {"total": 0, "errors": 0}
        await _run_phase(
            client,
            base_url,
            read_ratio,
            duration_s,
            concurrency,
            key_space,
            focus_pool,
            focus_share,
            latencies,
            counters,
        )

        m = await client.get(f"{base_url}/metrics", timeout=30.0)
        m.raise_for_status()
        metrics_after = m.json()

    total = counters["total"]
    elapsed = duration_s
    thr = total / elapsed if elapsed > 0 else 0.0
    latencies.sort()
    avg = sum(latencies) / len(latencies) if latencies else 0.0
    p95 = latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0.0

    return LoadResult(
        label=label,
        base_url=base_url,
        read_ratio=read_ratio,
        duration_s=duration_s,
        concurrency=concurrency,
        key_space=key_space,
        seed_rows=seed_rows,
        warmup_seconds=warmup_seconds,
        focus_pool=focus_pool,
        focus_share=focus_share,
        total_requests=total,
        errors=counters["errors"],
        throughput_rps=thr,
        avg_latency_ms=avg,
        p95_latency_ms=p95,
        metrics_after=metrics_after,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="KV cache load generator (unified test)")
    p.add_argument("--url", required=True, help="Base URL of one app instance")
    p.add_argument("--read-ratio", type=float, default=0.8, help="Share of GET vs PUT (0..1)")
    p.add_argument("--duration", type=float, default=30.0, help="Seconds of sustained load")
    p.add_argument("--concurrency", type=int, default=40, help="Concurrent asyncio workers")
    p.add_argument("--key-space", type=int, default=10_000, help="Keys are 0 .. key-space-1")
    p.add_argument("--seed-rows", type=int, default=10_000, help="Rows inserted by /admin/reset")
    p.add_argument(
        "--warmup-seconds",
        type=float,
        default=0.0,
        help="After /admin/reset, run load this long without recording latency; then reset server counters",
    )
    p.add_argument(
        "--focus-pool",
        type=int,
        default=0,
        help="If >0, focus_share of keys are drawn uniformly from [0, min(focus_pool,key_space)-1]",
    )
    p.add_argument(
        "--focus-share",
        type=float,
        default=0.85,
        help="Used when focus-pool > 0: fraction of requests hitting the hot key pool",
    )
    p.add_argument("--label", default="", help="Tag for JSON output")
    p.add_argument("--json-out", default="", help="If set, write full result JSON to this path")
    args = p.parse_args()

    label = args.label or f"read_ratio={args.read_ratio}"

    result = asyncio.run(
        run_load(
            args.url,
            args.read_ratio,
            args.duration,
            args.concurrency,
            args.key_space,
            args.seed_rows,
            label,
            warmup_seconds=args.warmup_seconds,
            focus_pool=args.focus_pool,
            focus_share=args.focus_share,
        )
    )

    d = asdict(result)
    line = json.dumps(d, ensure_ascii=False)
    print(line)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(line + "\n")

    print(
        f"\n[{label}] url={args.url} read={args.read_ratio:.0%} "
        f"req={result.total_requests} err={result.errors} "
        f"rps={result.throughput_rps:.1f} avg_ms={result.avg_latency_ms:.2f} p95_ms={result.p95_latency_ms:.2f}",
        file=sys.stderr,
    )
    m = result.metrics_after
    print(
        f"  server_metrics: db_reads={m.get('db_reads')} db_writes={m.get('db_writes')} "
        f"cache_hit_rate={m.get('cache_hit_rate')} hit/miss={m.get('cache_hits')}/{m.get('cache_misses')}",
        file=sys.stderr,
    )
    if m.get("write_back_dirty_keys_pending") is not None:
        print(
            f"  write_back: dirty_pending={m.get('write_back_dirty_keys_pending')} "
            f"flushed_total={m.get('write_back_dirty_keys_flushed_total')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()

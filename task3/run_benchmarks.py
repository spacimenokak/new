"""
Runs the same unified load test for all three strategies (three base URLs).
Order: cache_aside, write_through, write_back.

Example (Docker Compose on localhost):
  python run_benchmarks.py \\
    --cache-aside http://127.0.0.1:8001 \\
    --write-through http://127.0.0.1:8002 \\
    --write-back http://127.0.0.1:8003 \\
    --duration 30 --concurrency 40
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from load_generator import run_load


async def _run_all(
    urls: dict[str, str],
    duration: float,
    concurrency: int,
    key_space: int,
    seed_rows: int,
    read_profiles: list[tuple[str, float]],
    warmup_seconds: float,
    focus_pool: int,
    focus_share: float,
) -> list[dict]:
    rows: list[dict] = []
    for profile_name, read_ratio in read_profiles:
        for strat, url in urls.items():
            res = await run_load(
                url,
                read_ratio,
                duration,
                concurrency,
                key_space,
                seed_rows,
                label=f"{strat}:{profile_name}",
                warmup_seconds=warmup_seconds,
                focus_pool=focus_pool,
                focus_share=focus_share,
            )
            row = {
                "strategy": strat,
                "profile": profile_name,
                "read_ratio": read_ratio,
                "warmup_seconds": res.warmup_seconds,
                "focus_pool": res.focus_pool,
                "focus_share": res.focus_share,
                "throughput_rps": res.throughput_rps,
                "avg_latency_ms": res.avg_latency_ms,
                "p95_latency_ms": res.p95_latency_ms,
                "total_requests": res.total_requests,
                "errors": res.errors,
                "db_reads": res.metrics_after.get("db_reads"),
                "db_writes": res.metrics_after.get("db_writes"),
                "cache_hit_rate": res.metrics_after.get("cache_hit_rate"),
                "cache_hits": res.metrics_after.get("cache_hits"),
                "cache_misses": res.metrics_after.get("cache_misses"),
                "write_back_dirty_pending": res.metrics_after.get("write_back_dirty_keys_pending"),
                "write_back_flushed_total": res.metrics_after.get(
                    "write_back_dirty_keys_flushed_total"
                ),
            }
            rows.append(row)
            print(
                f"{strat:14} {profile_name:12} rps={res.throughput_rps:8.1f} "
                f"avg_ms={res.avg_latency_ms:7.2f} db_r={row['db_reads']} db_w={row['db_writes']} "
                f"hit_rate={row['cache_hit_rate']}"
            )
    return rows


def _markdown_table(rows: list[dict]) -> str:
    headers = [
        "strategy",
        "profile",
        "read%",
        "rps",
        "avg_ms",
        "db_reads",
        "db_writes",
        "hit_rate",
        "wb_dirty",
        "wb_flushed",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        rp = int(round(r["read_ratio"] * 100))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(r["strategy"]),
                    str(r["profile"]),
                    str(rp),
                    f"{r['throughput_rps']:.1f}",
                    f"{r['avg_latency_ms']:.2f}",
                    str(r["db_reads"]),
                    str(r["db_writes"]),
                    str(r["cache_hit_rate"]),
                    str(r.get("write_back_dirty_pending")),
                    str(r.get("write_back_flushed_total")),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache-aside", required=True)
    ap.add_argument("--write-through", required=True)
    ap.add_argument("--write-back", required=True)
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=40)
    ap.add_argument("--key-space", type=int, default=10_000)
    ap.add_argument("--seed-rows", type=int, default=10_000)
    ap.add_argument("--out-json", default="benchmark_results.json")
    ap.add_argument("--out-md", default="benchmark_table.md")
    ap.add_argument(
        "--warmup-seconds",
        type=float,
        default=0.0,
        help="Same load profile before each timed run; then POST /admin/reset-counters (cache stays warm)",
    )
    ap.add_argument(
        "--focus-pool",
        type=int,
        default=0,
        help="Hot subset size for key locality (0 = uniform over full key_space)",
    )
    ap.add_argument(
        "--focus-share",
        type=float,
        default=0.85,
        help="Fraction of requests hitting focus-pool when focus-pool > 0",
    )
    args = ap.parse_args()

    urls = {
        "cache_aside": args.cache_aside.rstrip("/"),
        "write_through": args.write_through.rstrip("/"),
        "write_back": args.write_back.rstrip("/"),
    }
    read_profiles = [
        ("read_heavy", 0.8),
        ("balanced", 0.5),
        ("write_heavy", 0.2),
    ]

    rows = asyncio.run(
        _run_all(
            urls,
            args.duration,
            args.concurrency,
            args.key_space,
            args.seed_rows,
            read_profiles,
            args.warmup_seconds,
            args.focus_pool,
            args.focus_share,
        )
    )

    Path(args.out_json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    Path(args.out_md).write_text(_markdown_table(rows), encoding="utf-8")
    print(f"\nWrote {args.out_json} and {args.out_md}")


if __name__ == "__main__":
    main()

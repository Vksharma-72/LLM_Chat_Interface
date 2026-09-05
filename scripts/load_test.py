#!/usr/bin/env python3
"""Async load test (S9): virtual users doing mixed send/stream against the app.

Prerequisites — a running app + mock LLM with ELEVATED rate limits, e.g.:

    uv run python scripts/mock_llm_server.py &
    DATABASE_URL=postgresql+asyncpg://llmchat:llmchat@localhost:5432/llmchat_test \\
    REDIS_URL=redis://localhost:6379/1 LLM_API_URL=http://localhost:8001/v1 \\
    RATE_LIMIT_CHAT_PER_MIN=1000000 RATE_LIMIT_API_PER_HOUR=1000000 \\
    uv run uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 3100

Then:
    uv run python scripts/load_test.py --users 50 --duration 300

Prints p50/p95/p99 latency, error rate, and an LLM_MAX_CONCURRENT tuning hint.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import time

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:3100"
MOCK_REPLY_MARKER = "mock reply"


def percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(pct / 100 * len(sorted_values) - 1)))
    return sorted_values[index]


async def register_user(client: httpx.AsyncClient, user_index: int) -> tuple[str, str]:
    username = f"load_{int(time.time())}_{user_index}_{random.randint(0, 99999)}"
    response = await client.post(
        "/api/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "password123"},
    )
    response.raise_for_status()
    return username, response.json()["access_token"]


async def create_conversation(client: httpx.AsyncClient, token: str) -> str:
    response = await client.post(
        "/api/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Load test"},
    )
    response.raise_for_status()
    return response.json()["id"]


class Metrics:
    def __init__(self) -> None:
        self.send_ms: list[float] = []
        self.stream_ms: list[float] = []
        self.errors = 0
        self.too_many_requests = 0

    @property
    def total(self) -> int:
        return len(self.send_ms) + len(self.stream_ms) + self.errors


async def do_send(
    client: httpx.AsyncClient, token: str, conversation_id: str, content: str, metrics: Metrics
) -> None:
    start = time.perf_counter()
    try:
        response = await client.post(
            "/api/chat/send",
            headers={"Authorization": f"Bearer {token}"},
            json={"conversation_id": conversation_id, "content": content},
        )
        elapsed = (time.perf_counter() - start) * 1000
        if response.status_code == 200:
            metrics.send_ms.append(elapsed)
        else:
            metrics.errors += 1
            if response.status_code == 429:
                metrics.too_many_requests += 1
    except Exception:
        metrics.errors += 1


async def do_stream(
    client: httpx.AsyncClient, token: str, conversation_id: str, content: str, metrics: Metrics
) -> None:
    start = time.perf_counter()
    try:
        async with client.stream(
            "POST",
            "/api/chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"conversation_id": conversation_id, "content": content},
        ) as response:
            if response.status_code != 200:
                metrics.errors += 1
                if response.status_code == 429:
                    metrics.too_many_requests += 1
                await response.aread()
                return
            async for _ in response.aiter_lines():
                pass  # consume the whole SSE body
        metrics.stream_ms.append((time.perf_counter() - start) * 1000)
    except Exception:
        metrics.errors += 1


async def user_loop(
    user_index: int,
    client: httpx.AsyncClient,
    deadline: float,
    metrics: Metrics,
    stream_share: float,
) -> None:
    try:
        _, token = await register_user(client, user_index)
        conversation_id = await create_conversation(client, token)
    except Exception as exc:
        metrics.errors += 1
        print(f"  user {user_index}: setup failed ({exc})")
        return

    request_index = 0
    while time.monotonic() < deadline:
        request_index += 1
        content = f"load test message {user_index}-{request_index} — {MOCK_REPLY_MARKER} check"
        if random.random() < stream_share:
            await do_stream(client, token, conversation_id, content, metrics)
        else:
            await do_send(client, token, conversation_id, content, metrics)
        await asyncio.sleep(random.uniform(0.05, 0.2))  # small think-time


def tuning_hint(max_concurrent: int, p95_ms: float, too_many_requests: int) -> str:
    lines = [f"LLM_MAX_CONCURRENT = {max_concurrent}"]
    if too_many_requests:
        lines.append(
            f"  note: {too_many_requests} responses were 429s — raise the rate limits for load testing."
        )
    if p95_ms > 2000:
        lines.append(
            f"  p95 send latency is {p95_ms:.0f} ms with only {max_concurrent} concurrent LLM slots:"
            " requests are queueing on the semaphore — consider raising LLM_MAX_CONCURRENT."
        )
    elif p95_ms > 800:
        lines.append("  p95 latency is moderate; LLM_MAX_CONCURRENT looks close to saturation.")
    else:
        lines.append("  p95 latency is healthy; LLM_MAX_CONCURRENT is adequate for this load.")
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--duration", type=int, default=300, help="seconds of sustained load")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--stream-share", type=float, default=0.5)
    args = parser.parse_args()

    max_concurrent = int(os.environ.get("LLM_MAX_CONCURRENT", "2"))
    metrics = Metrics()
    deadline = time.monotonic() + args.duration
    started = time.perf_counter()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        print(f"==> Running {args.users} virtual users for {args.duration}s against {args.base_url}")
        await asyncio.gather(
            *(
                user_loop(index, client, deadline, metrics, args.stream_share)
                for index in range(args.users)
            )
        )

    wall_seconds = time.perf_counter() - started
    send_sorted = sorted(metrics.send_ms)
    stream_sorted = sorted(metrics.stream_ms)
    all_sorted = sorted(send_sorted + stream_sorted)
    total = metrics.total
    error_rate = (metrics.errors / total * 100) if total else 100.0

    def stat(values: list[float], pct: float) -> float:
        return percentile(values, pct) if values else 0.0

    print()
    print("============ LOAD TEST REPORT ============")
    print(f"  users / duration   : {args.users} / {args.duration}s (wall {wall_seconds:.0f}s)")
    print(f"  requests           : {total}  (send {len(send_sorted)}, stream {len(stream_sorted)})")
    print(f"  throughput         : {total / wall_seconds:.1f} req/s")
    print(
        "  errors             :"
        f" {metrics.errors} ({error_rate:.2f}%){' — incl. ' + str(metrics.too_many_requests) + ' x 429' if metrics.too_many_requests else ''}"
    )
    print(f"  latency p50/p95/p99: {stat(all_sorted, 50):.0f} / {stat(all_sorted, 95):.0f} / {stat(all_sorted, 99):.0f} ms (all)")
    print(f"  send    p50/p95/p99: {stat(send_sorted, 50):.0f} / {stat(send_sorted, 95):.0f} / {stat(send_sorted, 99):.0f} ms")
    print(f"  stream  p50/p95/p99: {stat(stream_sorted, 50):.0f} / {stat(stream_sorted, 95):.0f} / {stat(stream_sorted, 99):.0f} ms")
    print()
    print(tuning_hint(max_concurrent, stat(send_sorted, 95), metrics.too_many_requests))
    print("==========================================")

    return 0 if error_rate < 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

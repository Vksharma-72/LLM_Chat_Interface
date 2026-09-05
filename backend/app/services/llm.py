"""LLM gateway — the ONLY module that talks to the LLM upstream (§8).

OpenAI-compatible llama.cpp at LLM_API_URL. All HTTP calls run inside
asyncio.Semaphore(LLM_MAX_CONCURRENT). Retries (2×, 0.5 s then 1 s backoff)
apply only to connect errors/timeouts and HTTP 5xx — never 4xx or 429.
Model list is cached in Redis for 5 min, upstream health for 30 s. When a
Redis client is not provided, caching is disabled.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
from typing import Any, TypedDict

import httpx
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.services.cache import cache_get_json, cache_set_json

MODELS_CACHE_KEY = "llm:models"
MODELS_CACHE_TTL_SECONDS = 300
HEALTH_CACHE_KEY = "llm:health"
HEALTH_CACHE_TTL_SECONDS = 30
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.5, 1.0)


class LLMUnavailable(Exception):
    """Upstream unreachable: connect/timeout/5xx after retries."""


class LLMRateLimited(Exception):
    """Upstream answered 429."""


class LLMBadResponse(Exception):
    """Upstream answered 4xx (non-429) or returned a malformed payload/SSE."""


class LLMResult(TypedDict):
    content: str
    usage: dict[str, int] | None
    model: str


class LLMEvent(TypedDict, total=False):
    """Stream event: {"type": "delta"|"usage"|"done"|"error", ...} (§7/§8)."""

    type: str
    content: str
    usage: dict[str, int] | None
    model: str
    error: dict[str, str]


def _error_event(code: str, message: str) -> LLMEvent:
    return {"type": "error", "error": {"code": code, "message": message}}


class LLMService:
    def __init__(
        self, settings: Settings | None = None, redis: Redis | None = None
    ) -> None:
        self._settings = settings or get_settings()
        self._redis = redis
        self._semaphore = asyncio.Semaphore(self._settings.LLM_MAX_CONCURRENT)
        self._client: httpx.AsyncClient | None = None

    # --- plumbing -----------------------------------------------------------

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.LLM_API_URL,
                timeout=self._settings.LLM_TIMEOUT_SECONDS,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _auth_headers(self) -> dict[str, str]:
        if self._settings.LLM_API_KEY:
            return {"Authorization": f"Bearer {self._settings.LLM_API_KEY}"}
        return {}

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Non-streaming request with retries on connect errors/timeouts/5xx only."""
        for delay in (*RETRY_BACKOFF_SECONDS, None):
            try:
                async with self._semaphore:
                    response = await self._http().request(
                        method, path, json=json_body, headers=self._auth_headers()
                    )
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if delay is not None:
                    await asyncio.sleep(delay)
                    continue
                raise LLMUnavailable("LLM upstream unreachable") from exc
            if response.status_code >= 500:
                if delay is not None:
                    await asyncio.sleep(delay)
                    continue
                raise LLMUnavailable(
                    f"LLM upstream returned HTTP {response.status_code} after retries"
                )
            if response.status_code == 429:
                raise LLMRateLimited("LLM upstream rate limited us (HTTP 429)")
            if response.status_code >= 400:
                raise LLMBadResponse(
                    f"LLM upstream rejected the request (HTTP {response.status_code})"
                )
            return response
        raise LLMUnavailable("LLM upstream unreachable")  # pragma: no cover

    async def _resolve_model(self, model: str | None) -> str:
        if model:
            return model
        if self._settings.LLM_MODEL:
            return self._settings.LLM_MODEL
        models = await self.list_models()
        if not models:
            raise LLMUnavailable("LLM upstream reports no models")
        return models[0]

    @staticmethod
    def _build_messages(
        messages: Sequence[dict[str, str]], system_prompt: str | None
    ) -> list[dict[str, str]]:
        if system_prompt and system_prompt.strip():
            return [{"role": "system", "content": system_prompt}, *messages]
        return list(messages)

    # --- public contract (§8) -------------------------------------------------

    async def list_models(self) -> list[str]:
        if self._redis is not None:
            cached = await cache_get_json(self._redis, MODELS_CACHE_KEY)
            if cached is not None:
                return cached
        response = await self._request("GET", "/models")
        try:
            data = response.json()
            models = [str(entry["id"]) for entry in data["data"]]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise LLMBadResponse("LLM upstream /models payload malformed") from exc
        if self._redis is not None:
            await cache_set_json(
                self._redis, MODELS_CACHE_KEY, models, MODELS_CACHE_TTL_SECONDS
            )
        return models

    async def health(self) -> bool:
        """Upstream reachable — i.e. list_models() succeeds. Cached 30 s."""
        if self._redis is not None:
            cached = await cache_get_json(self._redis, HEALTH_CACHE_KEY)
            if cached is not None:
                return bool(cached)
        healthy = True
        try:
            await self._request("GET", "/models")
        except (LLMUnavailable, LLMRateLimited, LLMBadResponse):
            healthy = False
        if self._redis is not None:
            await cache_set_json(
                self._redis, HEALTH_CACHE_KEY, healthy, HEALTH_CACHE_TTL_SECONDS
            )
        return healthy

    async def chat_completion(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> LLMResult:
        resolved = await self._resolve_model(model)
        body: dict[str, Any] = {
            "model": resolved,
            "messages": self._build_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        response = await self._request("POST", "/chat/completions", json_body=body)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            raw_usage = data.get("usage")
            usage = (
                {
                    "prompt_tokens": int(raw_usage["prompt_tokens"]),
                    "completion_tokens": int(raw_usage["completion_tokens"]),
                }
                if raw_usage
                else None
            )
            result_model = data.get("model") or resolved
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMBadResponse("LLM upstream completion payload malformed") from exc
        return {"content": content, "usage": usage, "model": result_model}

    async def chat_completion_stream(
        self,
        messages: Sequence[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> AsyncIterator[LLMEvent]:
        """Yield delta/usage/done events; failures become {"type": "error"} events."""
        resolved = await self._resolve_model(model)
        body: dict[str, Any] = {
            "model": resolved,
            "messages": self._build_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with self._semaphore:  # held for the whole stream duration
            try:
                response = await self._open_stream(body)
            except LLMRateLimited as exc:
                yield _error_event("llm_rate_limited", str(exc))
                return
            except LLMBadResponse as exc:
                yield _error_event("llm_unavailable", str(exc))
                return
            except LLMUnavailable as exc:
                yield _error_event("llm_unavailable", str(exc))
                return

            usage: dict[str, int] | None = None
            model_seen: str | None = resolved
            try:
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError as exc:
                        raise LLMBadResponse("Malformed SSE from LLM upstream") from exc
                    if chunk.get("usage"):
                        usage = {
                            "prompt_tokens": int(chunk["usage"]["prompt_tokens"]),
                            "completion_tokens": int(chunk["usage"]["completion_tokens"]),
                        }
                        yield {"type": "usage", "usage": usage}
                    choices = chunk.get("choices") or []
                    if choices:
                        model_seen = chunk.get("model") or model_seen
                        content = (choices[0].get("delta") or {}).get("content")
                        if content:
                            yield {"type": "delta", "content": content}
            except LLMBadResponse as exc:
                yield _error_event("llm_unavailable", str(exc))
                return
            except (httpx.TimeoutException, httpx.ConnectError):
                yield _error_event(
                    "llm_unavailable", "Connection to LLM upstream lost mid-stream"
                )
                return
            finally:
                await response.aclose()

            yield {"type": "done", "usage": usage, "model": model_seen}

    async def _open_stream(self, body: dict[str, Any]) -> httpx.Response:
        """Open a streaming POST with the §8 retry policy (call within semaphore)."""
        for delay in (*RETRY_BACKOFF_SECONDS, None):
            try:
                response = await self._http().send(
                    self._http().build_request(
                        "POST", "/chat/completions", json=body, headers=self._auth_headers()
                    ),
                    stream=True,
                )
            except (httpx.TimeoutException, httpx.ConnectError):
                if delay is not None:
                    await asyncio.sleep(delay)
                    continue
                raise LLMUnavailable("LLM upstream unreachable")
            if response.status_code >= 500:
                await response.aclose()
                if delay is not None:
                    await asyncio.sleep(delay)
                    continue
                raise LLMUnavailable(
                    f"LLM upstream returned HTTP {response.status_code} after retries"
                )
            if response.status_code == 429:
                await response.aclose()
                raise LLMRateLimited("LLM upstream rate limited us (HTTP 429)")
            if response.status_code >= 400:
                await response.aclose()
                raise LLMBadResponse(
                    f"LLM upstream rejected the request (HTTP {response.status_code})"
                )
            return response
        raise LLMUnavailable("LLM upstream unreachable")  # pragma: no cover


@lru_cache
def get_llm_service() -> LLMService:
    """Process-wide service used by the API routes (from Step 5 on)."""
    redis = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return LLMService(redis=redis)

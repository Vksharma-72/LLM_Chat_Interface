"""Concurrency cap: all upstream HTTP calls run inside Semaphore(LLM_MAX_CONCURRENT)."""

import asyncio

import httpx
import respx
from app.core.config import get_settings
from app.services.llm import LLMService

COMPLETION_PAYLOAD = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "ok"}}],
}


async def test_semaphore_caps_concurrent_requests(llm_service, llm_url, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_MAX_CONCURRENT", 2)
    service = LLMService()  # fresh semaphore honoring the (patched) setting
    state = {"current": 0, "max": 0}

    async def slow_handler(request):
        state["current"] += 1
        state["max"] = max(state["max"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return httpx.Response(200, json=COMPLETION_PAYLOAD)

    with respx.mock:
        respx.post(f"{llm_url}/chat/completions").mock(side_effect=slow_handler)
        await asyncio.gather(
            *(
                service.chat_completion([{"role": "user", "content": f"msg-{i}"}])
                for i in range(4)
            )
        )

    assert state["max"] == 2
    await service.aclose()

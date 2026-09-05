"""Live tests against the real llama.cpp server — run only when LLM_LIVE_TEST=1.

Enable with:  LLM_API_URL=http://localhost:8000/v1  (plus optional LLM_API_KEY)
              LLM_LIVE_TEST=1  uv run pytest tests/llm/test_live.py -v
"""

import pytest
from app.core.config import get_settings
from app.services.llm import LLMService

pytestmark = pytest.mark.skipif(
    not get_settings().LLM_LIVE_TEST, reason="LLM_LIVE_TEST=0 (no real LLM server)"
)


async def test_live_models_completion_and_stream():
    service = LLMService()
    try:
        models = await service.list_models()
        assert models, "real server must report at least one model"

        result = await service.chat_completion(
            [{"role": "user", "content": "Say hi in one word."}], max_tokens=16
        )
        assert result["content"].strip()
        assert result["model"]

        events = [
            event
            async for event in service.chat_completion_stream(
                [{"role": "user", "content": "Say hi in one word."}], max_tokens=16
            )
        ]
        assert any(event["type"] == "delta" for event in events)
        assert events[-1]["type"] == "done"
    finally:
        await service.aclose()

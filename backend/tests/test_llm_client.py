"""Unit tests for Streaming LLM Client, Thinking Bypass, and Ollama Fallback."""

import unittest.mock
from typing import Any
import httpx
import openai
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
import pytest

from backend.app.core.llm_client import LLMClient


def create_mock_chunk(
    content: str | None = None,
    reasoning_content: str | None = None,
    empty_choices: bool = False,
) -> ChatCompletionChunk:
    """Helper creating a typed ChatCompletionChunk mock."""
    if empty_choices:
        choices = []
    else:
        delta = ChoiceDelta(content=content)
        # DeepSeek reasoning delta compatibility
        if reasoning_content is not None:
            delta.reasoning_content = reasoning_content  # type: ignore[attr-defined]
        choice = Choice(delta=delta, index=0)
        choices = [choice]

    return ChatCompletionChunk(
        id="test-chunk-id",
        choices=choices,
        created=1700000000,
        model="deepseek-flash",
        object="chat.completion.chunk",
    )


async def async_stream_generator(chunks: list[ChatCompletionChunk]):
    for c in chunks:
        yield c


class TestLLMClient:
    @pytest.mark.asyncio
    async def test_deepseek_streaming_thinking_disabled(self):
        """AC-1 / ADR-0006: Stream tokens from DeepSeek with extra_body thinking disabled."""
        mock_primary = unittest.mock.AsyncMock()
        mock_fallback = unittest.mock.AsyncMock()

        chunks = [
            create_mock_chunk("Hello "),
            create_mock_chunk("from "),
            create_mock_chunk("DeepSeek!"),
        ]
        mock_primary.chat.completions.create.return_value = async_stream_generator(chunks)

        client = LLMClient(
            api_key="<MOCK_API_KEY>",
            primary_client=mock_primary,
            fallback_client=mock_fallback,
        )

        messages = [{"role": "user", "content": "Hi"}]
        streamed = []
        async for token in client.stream_chat(messages):
            streamed.append(token)

        assert "".join(streamed) == "Hello from DeepSeek!"
        assert client.active_provider == "deepseek"
        assert not client.is_fallback

        mock_primary.chat.completions.create.assert_awaited_once()
        call_kwargs = mock_primary.chat.completions.create.call_args[1]
        assert call_kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}
        assert call_kwargs.get("stream") is True
        assert call_kwargs.get("model") == "deepseek-flash"

        # Fallback was not called
        mock_fallback.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_ollama_payload_isolation(self):
        """Acceptance Gate: Verify DeepSeek thinking flag and Ollama isolation (zero thinking keys)."""
        mock_primary = unittest.mock.AsyncMock()
        mock_fallback = unittest.mock.AsyncMock()

        # Simulate connection error on DeepSeek to trigger fallback
        req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        mock_primary.chat.completions.create.side_effect = openai.APIConnectionError(
            request=req, message="Connection refused"
        )

        ollama_chunks = [create_mock_chunk("Ollama response")]
        mock_fallback.chat.completions.create.return_value = async_stream_generator(ollama_chunks)

        client = LLMClient(
            api_key="<MOCK_API_KEY>",
            primary_client=mock_primary,
            fallback_client=mock_fallback,
        )

        tokens = []
        async for t in client.stream_chat([{"role": "user", "content": "Ping"}]):
            tokens.append(t)

        assert "".join(tokens) == "Ollama response"
        assert client.active_provider == "ollama"
        assert client.is_fallback is True

        # 1. Verify DeepSeek request had thinking disabled
        primary_kwargs = mock_primary.chat.completions.create.call_args[1]
        assert primary_kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}

        # 2. Verify Ollama fallback request payload
        fallback_kwargs = mock_fallback.chat.completions.create.call_args[1]
        assert fallback_kwargs.get("model") == "qwen2.5:3b"

        # CRITICAL PAYLOAD ISOLATION: Check extra_body and all kwargs for zero "thinking" key
        extra_body = fallback_kwargs.get("extra_body", {})
        assert "thinking" not in extra_body, "Ollama request must not contain thinking key in extra_body!"
        assert "thinking" not in fallback_kwargs, "Ollama request must not contain thinking kwarg!"

        # Ollama parameters must specify options with num_ctx=2048
        options = extra_body.get("options", {})
        assert options.get("num_ctx") == 2048
        assert "thinking" not in options

    @pytest.mark.asyncio
    async def test_failover_on_connection_error(self):
        """AC-2: Automatic fallback to Ollama on APIConnectionError without unhandled exception."""
        mock_primary = unittest.mock.AsyncMock()
        mock_fallback = unittest.mock.AsyncMock()

        req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        mock_primary.chat.completions.create.side_effect = openai.APIConnectionError(
            request=req, message="Offline"
        )
        mock_fallback.chat.completions.create.return_value = async_stream_generator(
            [create_mock_chunk("Fallback ok")]
        )

        client = LLMClient(
            api_key="<MOCK_API_KEY>",
            primary_client=mock_primary,
            fallback_client=mock_fallback,
        )

        result = [t async for t in client.stream_chat([{"role": "user", "content": "Test"}])]
        assert "".join(result) == "Fallback ok"
        assert client.active_provider == "ollama"

    @pytest.mark.asyncio
    async def test_failover_on_rate_limit_and_5xx(self):
        """AC-2: Automatic failover on HTTP 429 RateLimitError and HTTP 500 InternalServerError."""
        mock_primary = unittest.mock.AsyncMock()
        mock_fallback = unittest.mock.AsyncMock()

        # 1. Test HTTP 429
        req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        res_429 = httpx.Response(429, request=req)
        mock_primary.chat.completions.create.side_effect = openai.RateLimitError(
            message="Rate limit exceeded", response=res_429, body=None
        )
        mock_fallback.chat.completions.create.return_value = async_stream_generator(
            [create_mock_chunk("Recovered 429")]
        )

        client = LLMClient(primary_client=mock_primary, fallback_client=mock_fallback)
        out_429 = [t async for t in client.stream_chat([{"role": "user", "content": "Test 429"}])]
        assert "".join(out_429) == "Recovered 429"

        # 2. Test HTTP 500
        client.reset_provider()
        assert client.active_provider == "deepseek"
        res_500 = httpx.Response(500, request=req)
        mock_primary.chat.completions.create.side_effect = openai.InternalServerError(
            message="Server error", response=res_500, body=None
        )
        mock_fallback.chat.completions.create.return_value = async_stream_generator(
            [create_mock_chunk("Recovered 500")]
        )

        out_500 = [t async for t in client.stream_chat([{"role": "user", "content": "Test 500"}])]
        assert "".join(out_500) == "Recovered 500"
        assert client.active_provider == "ollama"

    @pytest.mark.asyncio
    async def test_stream_chunk_safety_empty_choices_and_reasoning_filter(self):
        """Guardrail: Empty choices do not crash stream; reasoning deltas are suppressed."""
        mock_primary = unittest.mock.AsyncMock()

        chunks = [
            create_mock_chunk(empty_choices=True),  # Metadata/empty chunk
            create_mock_chunk(content=None, reasoning_content="Thinking step 1"),
            create_mock_chunk(content="", reasoning_content="Thinking step 2"),
            create_mock_chunk(content="Spoken answer part 1. "),
            create_mock_chunk(content=None, reasoning_content="Thinking step 3"),
            create_mock_chunk(content="Spoken answer part 2."),
            create_mock_chunk(empty_choices=True),
        ]
        mock_primary.chat.completions.create.return_value = async_stream_generator(chunks)

        client = LLMClient(primary_client=mock_primary)
        tokens = [t async for t in client.stream_chat([{"role": "user", "content": "Query"}])]

        combined = "".join(tokens)
        assert combined == "Spoken answer part 1. Spoken answer part 2."
        assert "Thinking" not in combined

    @pytest.mark.asyncio
    async def test_non_streaming_chat_and_failover(self):
        """Non-streaming chat() method returns completion and handles failover."""
        mock_primary = unittest.mock.AsyncMock()
        mock_fallback = unittest.mock.AsyncMock()

        req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        mock_primary.chat.completions.create.side_effect = openai.APIConnectionError(
            request=req, message="Offline"
        )

        mock_completion = unittest.mock.MagicMock()
        mock_choice = unittest.mock.MagicMock()
        mock_choice.message.content = "Ollama non-stream reply"
        mock_completion.choices = [mock_choice]
        mock_fallback.chat.completions.create.return_value = mock_completion

        client = LLMClient(primary_client=mock_primary, fallback_client=mock_fallback)
        res = await client.chat([{"role": "user", "content": "Hello"}])

        assert res.choices[0].message.content == "Ollama non-stream reply"
        assert client.active_provider == "ollama"

    @pytest.mark.asyncio
    async def test_stream_chat_accumulates_tool_call_deltas(self):
        """Tool call deltas in stream_chat are accumulated into client.last_tool_calls."""
        mock_primary = unittest.mock.AsyncMock()

        # Mock tool call delta chunks
        chunk1 = unittest.mock.MagicMock()
        tc1 = unittest.mock.MagicMock()
        tc1.index = 0
        tc1.id = "call_abc"
        tc1.function.name = "search_web"
        tc1.function.arguments = '{"query": "'
        chunk1.choices = [unittest.mock.MagicMock(delta=unittest.mock.MagicMock(content=None, tool_calls=[tc1]))]

        chunk2 = unittest.mock.MagicMock()
        tc2 = unittest.mock.MagicMock()
        tc2.index = 0
        tc2.id = None
        tc2.function.name = None
        tc2.function.arguments = 'Python 3.12"}'
        chunk2.choices = [unittest.mock.MagicMock(delta=unittest.mock.MagicMock(content=None, tool_calls=[tc2]))]

        async def stream_tool_chunks():
            yield chunk1
            yield chunk2

        mock_primary.chat.completions.create.return_value = stream_tool_chunks()

        client = LLMClient(primary_client=mock_primary)
        tokens = [t async for t in client.stream_chat([{"role": "user", "content": "Search Python"}])]

        assert tokens == []
        assert len(client.last_tool_calls) == 1
        call = client.last_tool_calls[0]
        assert call["id"] == "call_abc"
        assert call["name"] == "search_web"
        assert call["arguments"] == '{"query": "Python 3.12"}'


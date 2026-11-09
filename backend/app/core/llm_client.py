"""Streaming LLM Client with DeepSeek thinking bypass and local Ollama failover."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator
import openai
from openai import AsyncOpenAI


class LLMClient:
    """Streaming LLM client targeting DeepSeek with thinking bypass and Ollama fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
        temperature: float = 0.7,
        fallback_url: str = "http://127.0.0.1:11434/v1",
        fallback_model: str = "qwen2.5:3b",
        timeout: float = 15.0,
        primary_client: AsyncOpenAI | None = None,
        fallback_client: AsyncOpenAI | None = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._fallback_model = fallback_model

        resolved_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "<MOCK_API_KEY>")
        self._primary_client = primary_client or AsyncOpenAI(
            api_key=resolved_api_key,
            base_url=base_url,
            timeout=timeout,
        )
        self._fallback_client = fallback_client or AsyncOpenAI(
            api_key="ollama",
            base_url=fallback_url,
            timeout=timeout,
        )

        self.active_provider: str = "deepseek"
        self.last_tool_calls: list[dict[str, Any]] = []

    @property
    def is_fallback(self) -> bool:
        """True if the client is actively routing requests to Ollama."""
        return self.active_provider == "ollama"

    def reset_provider(self) -> None:
        """Reset active provider back to primary DeepSeek client."""
        self.active_provider = "deepseek"

    def _should_failover(self, exc: Exception) -> bool:
        """Check if an exception warrants automatic failover to local Ollama."""
        if isinstance(
            exc,
            (
                openai.APIConnectionError,
                openai.APITimeoutError,
                openai.RateLimitError,
                openai.InternalServerError,
            ),
        ):
            return True
        if isinstance(exc, openai.APIStatusError):
            return exc.status_code >= 500 or exc.status_code == 429
        return False

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens delta by delta, handling thinking suppression and failover."""
        temp = temperature if temperature is not None else self._temperature
        kwargs: dict[str, Any] = {"tools": tools} if tools else {}

        self.last_tool_calls = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        yielded_any = False

        if self.active_provider == "deepseek":
            try:
                response = await self._primary_client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temp,
                    stream=True,
                    extra_body={"thinking": {"type": "disabled"}},
                    **kwargs,
                )
                async for chunk in response:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        yielded_any = True
                        yield content

                    delta_tool_calls = getattr(delta, "tool_calls", None)
                    if delta_tool_calls:
                        for tc in delta_tool_calls:
                            idx = getattr(tc, "index", 0)
                            if idx not in tool_calls_acc:
                                fn = getattr(tc, "function", None)
                                tool_calls_acc[idx] = {
                                    "id": getattr(tc, "id", "") or "",
                                    "name": getattr(fn, "name", "") if fn else "",
                                    "arguments": getattr(fn, "arguments", "") if fn else "",
                                }
                            else:
                                tc_id = getattr(tc, "id", "")
                                if tc_id:
                                    tool_calls_acc[idx]["id"] += tc_id
                                fn = getattr(tc, "function", None)
                                if fn:
                                    if getattr(fn, "name", ""):
                                        tool_calls_acc[idx]["name"] += fn.name
                                    if getattr(fn, "arguments", ""):
                                        tool_calls_acc[idx]["arguments"] += fn.arguments

                if tool_calls_acc:
                    self.last_tool_calls = list(tool_calls_acc.values())
                return
            except Exception as exc:
                if yielded_any or not self._should_failover(exc):
                    raise exc
                self.active_provider = "ollama"

        # Fallback provider: Local Ollama
        ollama_extra_body = {
            "options": {"num_ctx": 2048, "temperature": temp},
            "keep_alive": "2m",
        }
        fallback_response = await self._fallback_client.chat.completions.create(
            model=self._fallback_model,
            messages=messages,
            temperature=temp,
            stream=True,
            extra_body=ollama_extra_body,
            **kwargs,
        )
        async for chunk in fallback_response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content

            delta_tool_calls = getattr(delta, "tool_calls", None)
            if delta_tool_calls:
                for tc in delta_tool_calls:
                    idx = getattr(tc, "index", 0)
                    if idx not in tool_calls_acc:
                        fn = getattr(tc, "function", None)
                        tool_calls_acc[idx] = {
                            "id": getattr(tc, "id", "") or "",
                            "name": getattr(fn, "name", "") if fn else "",
                            "arguments": getattr(fn, "arguments", "") if fn else "",
                        }
                    else:
                        tc_id = getattr(tc, "id", "")
                        if tc_id:
                            tool_calls_acc[idx]["id"] += tc_id
                        fn = getattr(tc, "function", None)
                        if fn:
                            if getattr(fn, "name", ""):
                                tool_calls_acc[idx]["name"] += fn.name
                            if getattr(fn, "arguments", ""):
                                tool_calls_acc[idx]["arguments"] += fn.arguments

        if tool_calls_acc:
            self.last_tool_calls = list(tool_calls_acc.values())

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Execute non-streaming chat completion with automatic failover."""
        temp = temperature if temperature is not None else self._temperature
        kwargs: dict[str, Any] = {"tools": tools} if tools else {}

        if self.active_provider == "deepseek":
            try:
                return await self._primary_client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temp,
                    stream=False,
                    extra_body={"thinking": {"type": "disabled"}},
                    **kwargs,
                )
            except Exception as exc:
                if not self._should_failover(exc):
                    raise exc
                self.active_provider = "ollama"

        ollama_extra_body = {
            "options": {"num_ctx": 2048, "temperature": temp},
            "keep_alive": "2m",
        }
        return await self._fallback_client.chat.completions.create(
            model=self._fallback_model,
            messages=messages,
            temperature=temp,
            stream=False,
            extra_body=ollama_extra_body,
            **kwargs,
        )

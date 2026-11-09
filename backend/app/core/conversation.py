import json
from pathlib import Path
from typing import Any, AsyncIterator
import yaml
from backend.app.core.dispatcher import ToolDispatcher
from backend.app.core.llm_client import LLMClient
from backend.app.memory.session_db import SessionDB
from backend.app.memory.store import MarkdownStore

DEFAULT_CHARACTER_CONFIG: dict[str, Any] = {
    "name": "Nyx",
    "persona": {
        "archetype": "Tomboyish girl",
        "tone": "Reflective, witty, candid, low-energy warm",
        "language_policy": {
            "bilingual_comprehension": True,
            "spoken_language": "English",
            "indonesian_acknowledgments": ["siap", "oke", "santai", "ngerti"],
        },
    },
    "voice": {
        "model": "kokoro-v1.0.onnx",
        "voice_id": "af_nicole",
        "blend_enabled": True,
        "blend_voice_id": "am_onyx",
        "blend_weight": 0.65,
        "speed": 1.0,
        "pitch": 1.0,
    },
    "default_emotion": "neutral",
    "permitted_emotions": ["neutral", "happy", "sad", "surprised", "thinking"],
    "system_prompt": (
        "You are Nyx, a candid, reflective, and witty tomboyish girl.\n"
        "You speak in natural, succinct English. You effortlessly understand mixed Indonesian and English.\n"
        "Always anchor an emotion tag at the very start of your response, e.g. <emotion>happy</emotion>.\n"
        "Never use markdown formatting, code blocks, or bullet points in voice conversation turns."
    ),
}


def load_character_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load character YAML configuration with defensive default fallback."""
    candidates = []
    if config_path is not None:
        candidates.append(Path(config_path))
    else:
        candidates.extend(
            [
                Path("backend/config/character.yaml"),
                Path("config/character.yaml"),
                Path(__file__).resolve().parent.parent.parent / "config" / "character.yaml",
            ]
        )

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass

    return DEFAULT_CHARACTER_CONFIG


def estimate_tokens(text: str) -> int:
    """Fast rule-of-thumb token estimator (1 token ~= 4 chars)."""
    return max(1, len(text) // 4)


class ConversationManager:
    """Orchestrates persona, persistent memory, session history, and LLM streaming."""

    def __init__(
        self,
        character_config: dict[str, Any] | None = None,
        config_path: Path | str | None = None,
        memory_store: MarkdownStore | None = None,
        session_db: SessionDB | None = None,
        llm_client: LLMClient | None = None,
        dispatcher: ToolDispatcher | None = None,
        default_max_tokens: int = 2048,
    ) -> None:
        self.character_config = (
            character_config
            if character_config is not None
            else load_character_config(config_path)
        )
        self.memory_store = memory_store
        self.session_db = session_db
        self.llm_client = llm_client
        self.dispatcher = dispatcher
        self.default_max_tokens = default_max_tokens

    def _get_system_content(self) -> str:
        """Combine persona system prompt with long-term USER.md and MEMORY.md."""
        sections = [
            self.character_config.get(
                "system_prompt", DEFAULT_CHARACTER_CONFIG["system_prompt"]
            ).strip()
        ]

        if self.memory_store is not None:
            user_profile = self.memory_store.read_user_profile().strip()
            if user_profile:
                sections.append(f"## User Profile\n{user_profile}")

            memory_facts = self.memory_store.read_memory().strip()
            if memory_facts:
                sections.append(f"## Relevant Memory & Facts\n{memory_facts}")

        return "\n\n".join(sections)

    def assemble_prompt(
        self,
        session_id: str,
        user_message: str,
        max_tokens: int | None = None,
    ) -> list[dict[str, str]]:
        """Assemble system prompt, budgeted history (FIFO eviction), and current user turn."""
        budget_chars = (max_tokens or self.default_max_tokens) * 4
        system_content = self._get_system_content()
        system_msg = {"role": "system", "content": system_content}
        latest_user_msg = {"role": "user", "content": user_message}

        reserved_chars = len(system_content) + len(user_message)
        available_for_history = max(0, budget_chars - reserved_chars)

        history_turns: list[dict[str, Any]] = []
        if self.session_db is not None:
            history_turns = self.session_db.get_recent_turns(session_id, limit=100)

        # Deduplication guard: if tail turn is already the identical user message, ignore it
        if (
            history_turns
            and history_turns[-1].get("role") == "user"
            and history_turns[-1].get("content") == user_message
        ):
            history_turns = history_turns[:-1]

        # FIFO eviction: preserve the most recent turns that fit within available budget
        kept_turns: list[dict[str, Any]] = []
        running_chars = 0
        for turn in reversed(history_turns):
            turn_chars = len(turn.get("content", ""))
            if running_chars + turn_chars <= available_for_history:
                kept_turns.append(turn)
                running_chars += turn_chars
            else:
                break
        kept_turns.reverse()

        messages = [system_msg]
        for t in kept_turns:
            messages.append({"role": t["role"], "content": t["content"]})
        messages.append(latest_user_msg)

        return messages

    async def process_turn(
        self,
        session_id: str,
        user_message: str,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Record user turn, stream LLM response, handle tool calling loop, and yield text deltas."""
        # 1. Assemble prompt first before recording turn to avoid duplicate user turns
        messages = self.assemble_prompt(session_id, user_message)

        if self.session_db is not None:
            self.session_db.add_turn(session_id, "user", user_message)

        tools = self.dispatcher.get_schemas() if self.dispatcher is not None else None

        if self.llm_client is not None:
            collected_chunks: list[str] = []
            try:
                async for chunk in self.llm_client.stream_chat(
                    messages, temperature=temperature, tools=tools
                ):
                    collected_chunks.append(chunk)
                    yield chunk

                # 2. Tool calling execution loop (Scenario 2 / AC-6)
                last_tool_calls = getattr(self.llm_client, "last_tool_calls", None)
                if self.dispatcher is not None and last_tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc.get("id") or f"call_{i}",
                                    "type": "function",
                                    "function": {
                                        "name": tc["name"],
                                        "arguments": tc["arguments"],
                                    },
                                }
                                for i, tc in enumerate(last_tool_calls)
                            ],
                        }
                    )
                    for i, tc in enumerate(last_tool_calls):
                        call_id = tc.get("id") or f"call_{i}"
                        raw_args = tc.get("arguments", "{}")
                        try:
                            args = (
                                json.loads(raw_args)
                                if isinstance(raw_args, str) and raw_args.strip()
                                else raw_args
                            )
                            result = self.dispatcher.dispatch(tc["name"], args)
                        except Exception as exc:
                            result = {"error": str(exc)}

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(result)
                                if not isinstance(result, str)
                                else result,
                            }
                        )

                    # Hop 2: Verbalize tool results via streaming LLM
                    async for chunk in self.llm_client.stream_chat(
                        messages, temperature=temperature
                    ):
                        collected_chunks.append(chunk)
                        yield chunk
            finally:
                full_response = "".join(collected_chunks).strip()
                if self.session_db is not None and full_response:
                    self.session_db.add_turn(session_id, "assistant", full_response)

    async def generate_response(
        self,
        session_id: str,
        user_message: str,
        temperature: float | None = None,
    ) -> str:
        """Non-streaming convenience helper returning full assistant response."""
        messages = self.assemble_prompt(session_id, user_message)

        if self.session_db is not None:
            self.session_db.add_turn(session_id, "user", user_message)

        tools = self.dispatcher.get_schemas() if self.dispatcher is not None else None

        if self.llm_client is not None:
            response = await self.llm_client.chat(
                messages, temperature=temperature, tools=tools
            )
            content = ""
            msg = None
            if hasattr(response, "choices") and response.choices:
                msg = response.choices[0].message
                content = msg.content or ""
            elif isinstance(response, str):
                content = response
            elif isinstance(response, dict):
                content = response.get("content", "")

            # Tool calling non-streaming loop
            if msg and getattr(msg, "tool_calls", None) and self.dispatcher is not None:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    raw_args = tc.function.arguments
                    try:
                        args = (
                            json.loads(raw_args)
                            if isinstance(raw_args, str) and raw_args.strip()
                            else raw_args
                        )
                        result = self.dispatcher.dispatch(tc.function.name, args)
                    except Exception as exc:
                        result = {"error": str(exc)}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result)
                            if not isinstance(result, str)
                            else result,
                        }
                    )

                final_resp = await self.llm_client.chat(messages, temperature=temperature)
                if hasattr(final_resp, "choices") and final_resp.choices:
                    content = final_resp.choices[0].message.content or ""
                elif isinstance(final_resp, str):
                    content = final_resp

            if self.session_db is not None and content:
                self.session_db.add_turn(session_id, "assistant", content)
            return content

        return ""

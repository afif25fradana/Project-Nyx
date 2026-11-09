from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.app.core.conversation import ConversationManager, load_character_config, estimate_tokens
from backend.app.memory.session_db import SessionDB
from backend.app.memory.store import MarkdownStore


def test_load_character_config_from_file():
    config = load_character_config()
    assert config["name"] == "Nyx"
    assert "tomboyish girl" in config["system_prompt"].lower()
    assert "<emotion>" in config["system_prompt"]


def test_load_character_config_default_fallback():
    config = load_character_config("non_existent_path.yaml")
    assert config["name"] == "Nyx"
    assert "system_prompt" in config
    assert len(config["system_prompt"]) > 20


def test_assemble_prompt_includes_persona_user_profile_memory(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    store.write_user_profile("Name: Alex\nInterests: AI, Vintage electronics")
    store.write_memory("Alex prefers concise answers and tea over coffee.")

    db = SessionDB(":memory:")
    manager = ConversationManager(memory_store=store, session_db=db)

    messages = manager.assemble_prompt("sess_1", "What's my name?")

    assert len(messages) == 2
    system_msg = messages[0]
    assert system_msg["role"] == "system"
    assert "Alex" in system_msg["content"]
    assert "Vintage electronics" in system_msg["content"]
    assert "concise answers and tea over coffee" in system_msg["content"]

    latest_msg = messages[1]
    assert latest_msg["role"] == "user"
    assert latest_msg["content"] == "What's my name?"

    db.close()


def test_assemble_prompt_history_chronological(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    db = SessionDB(":memory:")

    db.add_turn("sess_1", "user", "Hello Nyx", timestamp=100.0)
    db.add_turn("sess_1", "assistant", "Hey there, Alex.", timestamp=101.0)

    manager = ConversationManager(memory_store=store, session_db=db)
    messages = manager.assemble_prompt("sess_1", "What are we doing today?")

    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Hello Nyx"}
    assert messages[2] == {"role": "assistant", "content": "Hey there, Alex."}
    assert messages[3] == {"role": "user", "content": "What are we doing today?"}

    db.close()


def test_assemble_prompt_fifo_budget_eviction(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    db = SessionDB(":memory:")

    # Add 10 turns of varying lengths
    for i in range(1, 11):
        role = "user" if i % 2 != 0 else "assistant"
        db.add_turn("sess_1", role, f"Turn {i} with some additional conversational text filler.", timestamp=100.0 + i)

    manager = ConversationManager(memory_store=store, session_db=db)

    # Calculate token budget that allows system prompt + latest message + only ~2-3 turns
    system_text = manager._get_system_content()
    user_msg = "Latest user message"
    base_chars = len(system_text) + len(user_msg)
    # Extra budget for approximately 2 turns (~120 chars)
    tight_budget_tokens = (base_chars + 120) // 4

    messages = manager.assemble_prompt("sess_1", user_msg, max_tokens=tight_budget_tokens)

    # 1. System prompt at index 0 MUST be preserved
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == system_text

    # 2. Latest user message at final index MUST be preserved
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == user_msg

    # 3. Oldest turns (Turn 1, Turn 2, etc.) MUST be evicted first (FIFO)
    all_contents = [m["content"] for m in messages]
    assert "Turn 1 with some additional conversational text filler." not in all_contents
    assert "Turn 2 with some additional conversational text filler." not in all_contents

    # 4. Kept turns must be the newest and in chronological order
    middle_turns = messages[1:-1]
    assert len(middle_turns) >= 1
    assert "Turn 10" in middle_turns[-1]["content"]

    db.close()


@pytest.mark.asyncio
async def test_process_turn_streaming(tmp_path: Path):
    db = SessionDB(":memory:")

    mock_llm = MagicMock()

    async def fake_stream(*args, **kwargs):
        for token in ["<emotion>happy</emotion> ", "Hello ", "Alex!"]:
            yield token

    mock_llm.stream_chat = fake_stream

    manager = ConversationManager(session_db=db, llm_client=mock_llm)

    chunks = []
    async for chunk in manager.process_turn("sess_1", "Hi Nyx"):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert full_output == "<emotion>happy</emotion> Hello Alex!"

    # Verify turns recorded in SessionDB
    turns = db.get_recent_turns("sess_1")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "Hi Nyx"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "<emotion>happy</emotion> Hello Alex!"

    db.close()


@pytest.mark.asyncio
async def test_generate_response_non_streaming(tmp_path: Path):
    db = SessionDB(":memory:")

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Non-streaming answer"
    mock_response.choices = [mock_choice]
    mock_llm.chat = AsyncMock(return_value=mock_response)

    manager = ConversationManager(session_db=db, llm_client=mock_llm)

    resp = await manager.generate_response("sess_1", "Direct question")
    assert resp == "Non-streaming answer"

    turns = db.get_recent_turns("sess_1")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "Direct question"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "Non-streaming answer"

    db.close()


@pytest.mark.asyncio
async def test_process_turn_no_user_turn_duplication(tmp_path: Path):
    db = SessionDB(":memory:")
    mock_llm = MagicMock()
    captured_messages = []

    async def fake_stream(messages, *args, **kwargs):
        captured_messages.extend(messages)
        yield "Response"

    mock_llm.stream_chat = fake_stream
    manager = ConversationManager(session_db=db, llm_client=mock_llm)

    async for _ in manager.process_turn("sess_1", "Single turn"):
        pass

    # Messages sent to LLM should be exactly: system, then single user message
    user_msgs = [m for m in captured_messages if m["role"] == "user"]
    assert len(user_msgs) == 1, f"Expected exactly 1 user message in prompt, got: {user_msgs}"
    assert user_msgs[0]["content"] == "Single turn"

    db.close()


@pytest.mark.asyncio
async def test_process_turn_executes_tool_calling_loop(tmp_path: Path):
    db = SessionDB(":memory:")
    mock_dispatcher = MagicMock()
    mock_dispatcher.get_schemas.return_value = [{"type": "function", "function": {"name": "add_todo"}}]
    mock_dispatcher.dispatch.return_value = {"id": 1, "title": "Buy milk", "status": "pending"}

    mock_llm = MagicMock()
    call_count = 0

    async def fake_stream_with_tool(messages, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First hop: model triggers tool call (no text content emitted)
            mock_llm.last_tool_calls = [
                {"id": "call_1", "name": "add_todo", "arguments": '{"title": "Buy milk"}'}
            ]
            return
        else:
            # Second hop: model verbalizes tool result
            mock_llm.last_tool_calls = []
            for token in ["<emotion>happy</emotion> ", "Added buy milk to your todos!"]:
                yield token

    mock_llm.stream_chat = fake_stream_with_tool
    mock_llm.last_tool_calls = []

    manager = ConversationManager(session_db=db, llm_client=mock_llm, dispatcher=mock_dispatcher)

    chunks = []
    async for chunk in manager.process_turn("sess_1", "Add buy milk to my todos"):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert "Added buy milk to your todos!" in full_output
    assert call_count == 2, f"Expected 2 LLM calls (tool call + verbalization), got {call_count}"
    mock_dispatcher.dispatch.assert_called_once_with("add_todo", {"title": "Buy milk"})

    db.close()


@pytest.mark.asyncio
async def test_process_turn_partial_stream_persists_on_interrupt(tmp_path: Path):
    db = SessionDB(":memory:")
    mock_llm = MagicMock()

    async def fake_stream(*args, **kwargs):
        yield "Chunk 1 "
        yield "Chunk 2 "
        yield "Chunk 3 "

    mock_llm.stream_chat = fake_stream
    manager = ConversationManager(session_db=db, llm_client=mock_llm)

    # Consumer cancels/breaks after receiving only the first chunk
    gen = manager.process_turn("sess_1", "Interrupted query")
    async for chunk in gen:
        assert chunk == "Chunk 1 "
        break  # Simulating barge-in / early cancellation
    await gen.aclose()

    # Verify that partial response was preserved in SessionDB
    turns = db.get_recent_turns("sess_1")
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "Chunk 1"

    db.close()


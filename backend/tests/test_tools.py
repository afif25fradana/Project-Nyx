from pathlib import Path
from unittest.mock import MagicMock
import pytest
from backend.app.core.dispatcher import ToolDispatcher
from backend.app.tools.todo_tools import TodoStore, validate_int
from backend.app.tools.search_tools import SearchClient


def test_todo_store_wal_and_pragmas(tmp_path: Path):
    db_file = tmp_path / "todos.db"
    store = TodoStore(db_file)

    cursor = store._conn.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"

    cursor = store._conn.execute("PRAGMA busy_timeout;")
    timeout = cursor.fetchone()[0]
    assert timeout == 5000

    store.close()


def test_todo_store_crud_and_harmonized_schema(tmp_path: Path):
    store = TodoStore(tmp_path / "todos.db")

    # Add todo
    todo = store.add_todo(title="Read documentation", category="research")
    assert todo["id"] == 1
    assert todo["title"] == "Read documentation"
    assert todo["category"] == "research"
    assert todo["status"] == "pending"
    assert todo["completed"] == 0
    assert "created_at" in todo
    assert todo["completed_at"] is None

    # Get todo
    fetched = store.get_todo(1)
    assert fetched is not None
    assert fetched["title"] == "Read documentation"

    # Complete todo
    completed = store.complete_todo(1)
    assert completed["status"] == "completed"
    assert completed["completed"] == 1
    assert completed["completed_at"] is not None

    # List todos filtering
    pending_list = store.list_todos(status="pending")
    assert len(pending_list) == 0

    completed_list = store.list_todos(status="completed")
    assert len(completed_list) == 1
    assert completed_list[0]["id"] == 1

    all_list = store.list_todos(status="all")
    assert len(all_list) == 1

    # Delete todo
    assert store.delete_todo(1) is True
    assert store.get_todo(1) is None
    assert store.delete_todo(999) is False

    store.close()


def test_todo_store_strict_integer_validation(tmp_path: Path):
    store = TodoStore(tmp_path / "todos.db")
    store.add_todo(title="Task 1")

    # In Python isinstance(True, int) is True, but INV 11 strictly rejects bool
    with pytest.raises(ValueError, match="must be an int"):
        store.complete_todo(True)

    with pytest.raises(ValueError, match="must be an int"):
        store.complete_todo(False)

    with pytest.raises(ValueError, match="must be an int"):
        store.complete_todo("1")

    with pytest.raises(ValueError, match="must be an int"):
        store.complete_todo(1.0)

    with pytest.raises(ValueError, match="must be an int"):
        store.get_todo(True)

    with pytest.raises(ValueError, match="must be an int"):
        store.delete_todo(True)

    # Verify task 1 remains uncompleted
    todo1 = store.get_todo(1)
    assert todo1["completed"] == 0
    assert todo1["status"] == "pending"

    store.close()


def test_search_client_empty_query():
    mock_tavily = MagicMock()
    client = SearchClient(tavily_client=mock_tavily)

    assert client.search("") == []
    assert client.search("   ") == []
    mock_tavily.search.assert_not_called()


def test_search_client_tavily_primary():
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = {
        "results": [
            {"title": "FastAPI Guide", "url": "https://fastapi.tiangolo.com", "content": "Modern web framework"}
        ]
    }
    client = SearchClient(api_key="<MOCK_TAVILY_KEY>", tavily_client=mock_tavily)

    results = client.search("FastAPI")
    assert len(results) == 1
    item = results[0]
    assert item["title"] == "FastAPI Guide"
    assert item["url"] == "https://fastapi.tiangolo.com"
    assert item["snippet"] == "Modern web framework"
    assert item["content"] == "Modern web framework"
    mock_tavily.search.assert_called_once_with(query="FastAPI", max_results=5)


def test_search_client_ddgs_fallback():
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = RuntimeError("Tavily quota exceeded")

    mock_ddgs = MagicMock()
    mock_ddgs.text.return_value = [
        {"title": "DuckDuckGo Python", "href": "https://duckduckgo.com/python", "body": "Python search results"}
    ]

    client = SearchClient(
        api_key="<MOCK_TAVILY_KEY>",
        tavily_client=mock_tavily,
        ddgs_client=mock_ddgs,
    )

    results = client.search("python programming")
    assert len(results) == 1
    item = results[0]
    assert item["title"] == "DuckDuckGo Python"
    assert item["url"] == "https://duckduckgo.com/python"
    assert item["snippet"] == "Python search results"
    assert item["content"] == "Python search results"


def test_search_client_ttl_cache():
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = {
        "results": [{"title": "Cached Title", "url": "https://cached.com", "content": "Cached Content"}]
    }
    client = SearchClient(api_key="<MOCK_TAVILY_KEY>", tavily_client=mock_tavily)

    res1 = client.search("Cached Query")
    # Second search with varying casing and whitespace
    res2 = client.search("   cached query   ")

    assert res1 == res2
    # Verify downstream was only called once (0 additional network calls per AC-7)
    assert mock_tavily.search.call_count == 1


def test_search_client_no_negative_caching():
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = RuntimeError("Tavily down")
    mock_ddgs = MagicMock()
    mock_ddgs.text.side_effect = RuntimeError("DDGS down")

    client = SearchClient(tavily_client=mock_tavily, ddgs_client=mock_ddgs)
    res = client.search("failing query")
    assert res == []

    # Verify query is not cached on failure
    assert "failing query" not in client._cache


def test_tool_dispatcher_schemas(tmp_path: Path):
    store = TodoStore(tmp_path / "todos.db")
    search = SearchClient()
    dispatcher = ToolDispatcher(todo_store=store, search_client=search)

    schemas = dispatcher.get_schemas()
    assert len(schemas) == 4
    names = [s["function"]["name"] for s in schemas]
    assert "add_todo" in names
    assert "complete_todo" in names
    assert "list_todos" in names
    assert "search_web" in names

    store.close()


def test_tool_dispatcher_dispatch_and_json_args(tmp_path: Path):
    store = TodoStore(tmp_path / "todos.db")
    search = SearchClient()
    dispatcher = ToolDispatcher(todo_store=store, search_client=search)

    # Dispatch with JSON string arguments
    added = dispatcher.dispatch("add_todo", '{"title": "Buy groceries", "category": "personal"}')
    assert added["id"] == 1
    assert added["title"] == "Buy groceries"

    # Dispatch with dict arguments
    pending = dispatcher.dispatch("list_todos", {"status": "pending"})
    assert len(pending) == 1

    # Complete todo
    completed = dispatcher.dispatch("complete_todo", {"todo_id": 1})
    assert completed["status"] == "completed"
    assert completed["completed"] == 1

    store.close()


def test_tool_dispatcher_strict_int_validation_in_dispatch(tmp_path: Path):
    store = TodoStore(tmp_path / "todos.db")
    dispatcher = ToolDispatcher(todo_store=store)

    # Boolean True in dict
    with pytest.raises(ValueError, match="must be an int"):
        dispatcher.dispatch("complete_todo", {"todo_id": True})

    # Boolean true in JSON string
    with pytest.raises(ValueError, match="must be an int"):
        dispatcher.dispatch("complete_todo", '{"todo_id": true}')

    store.close()


def test_tool_dispatcher_unknown_tool():
    dispatcher = ToolDispatcher()
    with pytest.raises(ValueError, match="Unknown tool"):
        dispatcher.dispatch("non_existent_tool", {})


def test_search_client_cache_capacity_and_eviction():
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = lambda query, max_results: {
        "results": [{"title": f"Result for {query}", "url": f"https://example.com/{query}", "content": "Sample"}]
    }

    client = SearchClient(tavily_client=mock_tavily, max_cache_size=3)

    # Add 4 queries to a cache with max_cache_size=3
    client.search("query1")
    client.search("query2")
    client.search("query3")
    assert len(client._cache) == 3

    client.search("query4")
    # Capacity must remain <= 3
    assert len(client._cache) == 3
    assert "query4" in client._cache
    # Oldest key (query1) should have been evicted
    assert "query1" not in client._cache


@pytest.mark.asyncio
async def test_todo_store_synchronous_normal_and_async_methods(tmp_path: Path):
    db_file = tmp_path / "todos.db"
    todo_store = TodoStore(db_file)

    cursor = todo_store._conn.execute("PRAGMA synchronous;")
    sync_mode = cursor.fetchone()[0]
    assert sync_mode == 1

    await todo_store.async_add_todo("task1", "test")
    todos = await todo_store.async_list_todos()
    assert len(todos) == 1
    assert todos[0]["title"] == "task1"

    todo_store.close()


def test_search_client_resolves_tavily_key_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-env-key-99")
    client = SearchClient()
    assert client._api_key == "tvly-test-env-key-99"



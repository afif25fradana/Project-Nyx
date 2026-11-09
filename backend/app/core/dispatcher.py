import json
from typing import Any, Callable
from backend.app.tools.todo_tools import TodoStore, validate_int
from backend.app.tools.search_tools import SearchClient


class ToolDispatcher:
    """Central dispatcher for LLM tool/function calling with schema export & strict typing (INV 11)."""

    def __init__(
        self,
        todo_store: TodoStore | None = None,
        search_client: SearchClient | None = None,
    ) -> None:
        self.todo_store = todo_store
        self.search_client = search_client
        self._tools: dict[str, Callable[..., Any]] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

        self._register_defaults()

    def _register_defaults(self) -> None:
        if self.todo_store is not None:
            self.register_tool(
                name="add_todo",
                handler=self.todo_store.add_todo,
                schema={
                    "type": "function",
                    "function": {
                        "name": "add_todo",
                        "description": "Add a new task to the user's to-do list.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "The title of the task."},
                                "category": {
                                    "type": "string",
                                    "description": "Optional category tag.",
                                    "default": "general",
                                },
                            },
                            "required": ["title"],
                        },
                    },
                },
            )
            self.register_tool(
                name="complete_todo",
                handler=self.todo_store.complete_todo,
                schema={
                    "type": "function",
                    "function": {
                        "name": "complete_todo",
                        "description": "Mark an existing task as completed by integer ID.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "todo_id": {"type": "integer", "description": "The unique integer ID of the task."}
                            },
                            "required": ["todo_id"],
                        },
                    },
                },
            )
            self.register_tool(
                name="list_todos",
                handler=self.todo_store.list_todos,
                schema={
                    "type": "function",
                    "function": {
                        "name": "list_todos",
                        "description": "List tasks filtered by status ('pending', 'completed', 'all').",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "completed", "all"],
                                    "default": "pending",
                                }
                            },
                        },
                    },
                },
            )

        if self.search_client is not None:
            self.register_tool(
                name="search_web",
                handler=self.search_client.search,
                schema={
                    "type": "function",
                    "function": {
                        "name": "search_web",
                        "description": "Search the live web for real-time information or factual verification.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query keywords."}
                            },
                            "required": ["query"],
                        },
                    },
                },
            )

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool handler function and its OpenAPI schema."""
        self._tools[name] = handler
        if schema:
            self._schemas[name] = schema

    def get_schemas(self) -> list[dict[str, Any]]:
        """Export OpenAI-compatible function calling tool schemas."""
        return list(self._schemas.values())

    def dispatch(self, tool_name: str, arguments: dict[str, Any] | str) -> Any:
        """Validate argument types strictly and dispatch to registered tool handler (INV 11)."""
        if tool_name not in self._tools:
            raise ValueError(f"Unknown tool: '{tool_name}'")

        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        elif isinstance(arguments, dict):
            args = dict(arguments)
        else:
            raise TypeError(f"Arguments must be dict or JSON string, got {type(arguments).__name__}")

        # Strict integer type validation from tool schema
        schema = self._schemas.get(tool_name)
        if schema and "function" in schema and "parameters" in schema["function"]:
            props = schema["function"]["parameters"].get("properties", {})
            for key, prop_info in props.items():
                if prop_info.get("type") == "integer" and key in args:
                    args[key] = validate_int(key, args[key])

        handler = self._tools[tool_name]
        return handler(**args)

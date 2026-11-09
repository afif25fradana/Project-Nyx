#!/usr/bin/env python3
"""
Project Nyx — Unified Launcher CLI
Coordinates lifecycle startup, environment verification, and clean execution
for Backend (FastAPI), Desktop Pet (PySide6), and Web Hub (React/Vite).
"""

import argparse
import sys


def run_backend(args: argparse.Namespace) -> int:
    """Launch the Nyx Backend service on loopback."""
    print(f"[Nyx] Starting Backend daemon on {args.host}:{args.port}...")
    # In Phase 1 scaffolding, backend modules will be linked in Phase 2-4
    print("[Nyx] Backend daemon initialized (Phase 1 stub).")
    return 0


def run_pet(args: argparse.Namespace) -> int:
    """Launch the Tier 1 Floating Desktop Pet overlay."""
    print(f"[Nyx] Starting Desktop Pet connecting to {args.ws_url}...")
    # In Phase 1 scaffolding, desktop pet modules will be linked in Phase 5
    print("[Nyx] Desktop Pet initialized (Phase 1 stub).")
    return 0


def run_web(args: argparse.Namespace) -> int:
    """Launch the Tier 2 Web Hub dev server."""
    print(f"[Nyx] Starting Web Hub on port {args.port}...")
    # In Phase 1 scaffolding, web hub dev server will be spawned via npm/vite
    print("[Nyx] Web Hub initialized (Phase 1 stub).")
    return 0


def run_all(args: argparse.Namespace) -> int:
    """Launch all components (Backend, Desktop Pet, and Web Hub)."""
    print("[Nyx] Starting all Project Nyx components...")
    run_backend(args)
    if not args.headless:
        run_pet(args)
    run_web(args)
    print("[Nyx] All components initialized successfully.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Project Nyx Unified Launcher — Manage backend, desktop pet, and web hub services.",
        epilog="For more information, consult docs/PRD.md and architecture.md in the AI context.",
    )
    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="command",
        required=True,
        help="Subcommand to execute",
    )

    # Subcommand: backend
    backend_parser = subparsers.add_parser(
        "backend",
        help="Start the headless FastAPI audio and LLM backend service",
    )
    backend_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind (default: 127.0.0.1)",
    )
    backend_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765)",
    )
    backend_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development",
    )
    backend_parser.set_defaults(func=run_backend)

    # Subcommand: pet
    pet_parser = subparsers.add_parser(
        "pet",
        help="Start the Tier 1 PySide6 floating transparent desktop pet",
    )
    pet_parser.add_argument(
        "--ws-url",
        type=str,
        default="ws://127.0.0.1:8765/ws/avatar",
        help="WebSocket endpoint for pet avatar communication",
    )
    pet_parser.set_defaults(func=run_pet)

    # Subcommand: web
    web_parser = subparsers.add_parser(
        "web",
        help="Start the Tier 2 React 19 / Vite Web Hub frontend",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=5173,
        help="Port for the Vite development server (default: 5173)",
    )
    web_parser.set_defaults(func=run_web)

    # Subcommand: all
    all_parser = subparsers.add_parser(
        "all",
        help="Start all Nyx services simultaneously",
    )
    all_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Backend host address (default: 127.0.0.1)",
    )
    all_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Backend port (default: 8765)",
    )
    all_parser.add_argument(
        "--ws-url",
        type=str,
        default="ws://127.0.0.1:8765/ws/avatar",
        help="Avatar WebSocket URL",
    )
    all_parser.add_argument(
        "--headless",
        action="store_true",
        help="Run backend and web hub without the desktop pet GUI",
    )
    all_parser.set_defaults(func=run_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

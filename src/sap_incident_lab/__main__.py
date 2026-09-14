from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config import get_settings
from .logging_config import configure_logging


def _serve(argv: Sequence[str] | None = None) -> None:
    from .server import build_server

    settings = get_settings()
    configure_logging(settings.log_level)
    build_server().run()


def _probe(argv: Sequence[str] | None = None) -> None:
    """Synchronous Ollama smoke test, independent of MCP — see DESIGN.md milestone 1."""
    import json
    from time import monotonic

    import httpx

    settings = get_settings()
    payload = {
        "model": settings.model,
        "stream": False,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": (
                    "Synthetic log: connection timed out twice, then succeeded. "
                    "State the observed facts and one missing diagnostic fact. "
                    "Use at most 80 words."
                ),
            }
        ],
        "options": {
            "num_ctx": settings.num_ctx,
            "num_predict": 200,
            "temperature": 0,
        },
    }
    start = monotonic()
    response = httpx.post(
        f"{settings.ollama_url}/api/chat",
        json=payload,
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    elapsed = monotonic() - start
    body = response.json()
    print(json.dumps({"elapsed_seconds": round(elapsed, 2)}, indent=2))
    print(body.get("message", {}).get("content", ""))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sap-incident-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the stdio MCP server")
    subparsers.add_parser("probe", help="Synchronous Ollama connectivity smoke test")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _serve()
    elif args.command == "probe":
        _probe()


if __name__ == "__main__":
    main(sys.argv[1:])

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .config import config_path, get_settings
from .errors import ToolError
from .evidence.paths import PathRejected
from .logging_config import configure_logging


def _print_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, default=str))
        return
    for key, value in result.items():
        label = key.replace("_", " ").capitalize()
        if key == "checks":
            for check in value:
                print(f"{'PASS' if check['ok'] else 'FAIL'} {check['name']}: {check['detail']}")
                if check.get("next_step"):
                    print(f"  Next: {check['next_step']}")
        elif isinstance(value, list):
            print(label + ":")
            for item in value:
                print(f"  {item}")
        elif value is not None:
            print(f"{label}: {value}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sap-incident-lab",
        description="Set up once, import exported logs, then investigate them in Claude.",
    )
    parser.add_argument("--config", type=Path, help="Use a separate saved configuration file.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the stdio MCP server")
    setup_parser = subparsers.add_parser("setup", help="Create folders and register Claude Desktop")
    setup_parser.add_argument("--data-dir", type=Path)
    setup_parser.add_argument("--model")
    setup_parser.add_argument("--fallback-model")
    setup_parser.add_argument("--desktop-config", type=Path)
    setup_parser.add_argument("--no-desktop", action="store_true")
    setup_parser.add_argument(
        "--pull-model",
        action="store_true",
        help="Download the selected model using installed Ollama.",
    )
    benchmark_parser = subparsers.add_parser("benchmark", help="Compare Ollama models with a bounded extraction probe")
    benchmark_parser.add_argument("--models", nargs="+", help="Ollama model tags; defaults to the configured model")
    benchmark_parser.add_argument("--repeats", type=int, choices=range(1, 4), default=1)
    benchmark_parser.add_argument("--json", action="store_true")
    benchmark_parser.add_argument("--output", type=Path, help="Also save the JSON benchmark result here.")
    config_parser = subparsers.add_parser("config", help="Inspect or validate effective configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser("show")
    config_show.add_argument("--json", action="store_true")
    config_subparsers.add_parser("validate")
    setup_parser.add_argument(
        "--interactive", action="store_true", help="Prompt for data folder and model."
    )
    for name, help_text in (
        ("doctor", "Check folders, Ollama, model and a synthetic extraction"),
        ("probe", "Run the same diagnostics as doctor"),
    ):
        diagnostic = subparsers.add_parser(name, help=help_text)
        diagnostic.add_argument(
            "--no-extraction",
            action="store_true",
            help="Skip inference; readiness is only a configuration/connectivity check.",
        )
        diagnostic.add_argument("--json", action="store_true")
    importing = subparsers.add_parser(
        "import", help="Copy selected text exports and create their manifest"
    )
    importing.add_argument("incident_id")
    importing.add_argument("files", nargs="+", type=Path)
    importing.add_argument("--summary", default="")
    importing.add_argument("--encoding", default="utf-8")
    importing.add_argument("--sid")
    importing.add_argument("--timezone", help="Declared export timezone; omitted means unknown.")
    importing.add_argument("--classification", choices=("unclassified", "synthetic", "approved-real"), default="unclassified")
    importing.add_argument("--acknowledge-sensitive-data", action="store_true", help="Required for approved-real imports.")
    importing.add_argument("--json", action="store_true")
    demo = subparsers.add_parser(
        "demo", help="Import bundled synthetic evidence and show a walkthrough"
    )
    demo.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.config:
        os.environ["INCIDENT_LAB_CONFIG"] = str(args.config.expanduser().resolve())
    get_settings.cache_clear()
    try:
        if args.command == "setup":
            from .onboarding import setup

            if args.interactive:
                previous = get_settings()
                current_folder = (
                    previous.root.parent if previous.root else Path.home() / "SAPIncidentLabData"
                )
                folder = input(f"Data folder [{current_folder}]: ").strip()
                model = input(f"Ollama model [{previous.model}]: ").strip()
                args.data_dir = Path(folder).expanduser() if folder else args.data_dir
                args.model = model or args.model
            result = setup(
                data_dir=args.data_dir,
                model=args.model,
                fallback_model=args.fallback_model,
                desktop_config=args.desktop_config,
                register_desktop=not args.no_desktop,
            )
            get_settings.cache_clear()
            if args.pull_model:
                ollama = shutil.which("ollama")
                if not ollama:
                    raise ValueError(
                        "Ollama is not installed. Install and start Ollama, then rerun setup --pull-model."
                    )
                models = [result["model"]]
                if result.get("fallback_model"):
                    models.append(result["fallback_model"])
                for selected_model in dict.fromkeys(models):
                    subprocess.run([ollama, "pull", selected_model], check=True)
            _print_result(result, False)
            return
        settings = get_settings()
        if args.command == "config":
            safe = {
                "config_path": str(config_path()),
                "root": str(settings.root) if settings.root else None,
                "output": str(settings.output) if settings.output else None,
                "model": settings.model,
                "fallback_model": settings.fallback_model,
                "ollama_url": settings.ollama_url,
                "num_ctx": settings.num_ctx,
                "num_predict": settings.num_predict,
            }
            if args.config_action == "show":
                _print_result(safe, args.json)
            else:
                reason = settings.evidence_config_error()
                if reason:
                    raise ValueError(reason)
                print("Configuration is valid.")
            return
        if args.command == "serve":
            from .server import build_server

            configure_logging(settings.log_level)
            build_server().run()
        elif args.command in ("doctor", "probe"):
            from .diagnostics import doctor

            result = asyncio.run(doctor(settings, extraction=not args.no_extraction))
            _print_result(result, args.json)
            if not result["ready"]:
                raise SystemExit(1)
        elif args.command == "benchmark":
            from .benchmark import benchmark_models

            result = asyncio.run(benchmark_models(settings, args.models or [settings.model], args.repeats))
            if args.output:
                args.output.expanduser().resolve().write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                result["output"] = str(args.output.expanduser().resolve())
            _print_result(result, args.json)
        elif args.command == "import":
            from .onboarding import import_incident

            if args.classification == "approved-real" and not args.acknowledge_sensitive_data:
                raise ValueError("approved-real imports require --acknowledge-sensitive-data after classification and retention review")
            result = import_incident(
                settings,
                args.incident_id,
                args.files,
                summary=args.summary,
                encoding=args.encoding,
                sid=args.sid,
                timezone=args.timezone,
                classification=args.classification,
            )
            _print_result(result, args.json)
        elif args.command == "demo":
            from .onboarding import install_demo

            _print_result(install_demo(settings), args.json)
    except (
        ToolError,
        OSError,
        ValueError,
        LookupError,
        PathRejected,
        subprocess.CalledProcessError,
        ValidationError,
    ) as exc:
        message = exc.message + " " + exc.recovery if isinstance(exc, ToolError) else str(exc)
        print(f"Could not complete {args.command}: {message}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main(sys.argv[1:])

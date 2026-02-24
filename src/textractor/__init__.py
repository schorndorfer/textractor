import os
import sys

import uvicorn


def main() -> None:
    """Main CLI entry point - routes to server or subcommands."""
    # Check if a subcommand was provided
    if len(sys.argv) > 1:
        subcommand = sys.argv[1]

        if subcommand == "migrate-annotations":
            # Route to migration command
            from .cli.migrate import main as migrate_main
            sys.argv.pop(1)
            migrate_main()
            return

        elif subcommand == "export-project":
            # Route to export command
            from .cli.export import main as export_main
            sys.argv.pop(1)
            export_main()
            return

    # Default: run the server
    host = os.environ.get("TEXTRACTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("TEXTRACTOR_PORT", "8000"))

    uvicorn.run(
        "textractor.api.main:app",
        host=host,
        port=port,
        reload=False,
    )

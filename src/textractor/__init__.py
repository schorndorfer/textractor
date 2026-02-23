import os

import uvicorn


def main() -> None:
    host = os.environ.get("TEXTRACTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("TEXTRACTOR_PORT", "8000"))

    uvicorn.run(
        "textractor.api.main:app",
        host=host,
        port=port,
        reload=False,
    )

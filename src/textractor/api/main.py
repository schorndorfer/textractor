from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .dependencies import init_store, init_terminology
from .routers import annotations, documents
from .routers import terminology as terminology_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    doc_root = Path(os.environ.get("TEXTRACTOR_DOC_ROOT", "./data/documents"))
    snomed_dir = Path("./data/terminology/SnomedCT")

    init_store(doc_root)
    init_terminology(snomed_dir=snomed_dir)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Textractor API",
        description="Clinical entity annotation tool",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(documents.router)
    app.include_router(annotations.router)
    app.include_router(terminology_router.router)

    # Serve React build in production
    frontend_dist = Path(__file__).parent.parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")

    return app


app = create_app()

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import BASE_DIR, get_settings
from backend.database import check_db_connection, init_db
from backend.logger import logger
from backend.routers import (
    analytics,
    auth,
    datasets,
    forecasting,
    insights,
    reports,
    settings as settings_router,
    segmentation,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app_settings = get_settings()

app = FastAPI(
    title=app_settings.app_name,
    version="1.0.0",
    description="Local enterprise e-commerce analytics, CSV ingestion, RFM segmentation, demand forecasting, and reporting API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Check backend logs for details."},
    )


@app.get("/api/health", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check() -> dict:
    return {
        "status": "ok",
        "database_connected": check_db_connection(),
    }


init_db()

app.include_router(auth.router)
app.include_router(auth.alias_router)
app.include_router(datasets.router)
app.include_router(analytics.router)
app.include_router(segmentation.router)
app.include_router(forecasting.router)
app.include_router(insights.router)
app.include_router(reports.router)
app.include_router(settings_router.router)

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.get("/", include_in_schema=False)
def root_page() -> FileResponse:
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(status_code=404, content={"detail": "Frontend entry page not found."})  # type: ignore[return-value]
    return FileResponse(str(index_file))

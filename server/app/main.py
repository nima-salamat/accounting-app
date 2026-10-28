"""FastAPI application factory and lifecycle."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from accounting_app.config import ensure_data_dir
from manager.db import create_db, initialize_database
from server.app.api.auth import router as auth_router
from server.app.api.admin import router as admin_router
from server.app.api.custom_schemas import router as schema_router
from server.app.api.reports import router as reports_router
from server.app.api.resources import router as resources_router
from server.app.api.sales import router as sales_router
from server.app.config import API_PREFIX


@asynccontextmanager
async def lifespan(_app):
    ensure_data_dir()
    initialize_database()
    create_db()
    yield


app = FastAPI(
    title="Accounting App API",
    description="Versioned API for the Accounting App desktop client.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": app.version}


app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
app.include_router(resources_router, prefix=API_PREFIX)
app.include_router(sales_router, prefix=API_PREFIX)
app.include_router(reports_router, prefix=API_PREFIX)
app.include_router(schema_router, prefix=API_PREFIX)

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.routers import auth, commands, grid, health, monitor, ops, orders, pnl, runtime


def create_app() -> FastAPI:
    app = FastAPI(
        title="auto mobile API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(ops.router)
    app.include_router(auth.router)
    app.include_router(runtime.bot_router)
    app.include_router(runtime.market_router)
    app.include_router(runtime.config_router)
    app.include_router(grid.router)
    app.include_router(orders.router)
    app.include_router(pnl.router)
    app.include_router(commands.router)
    app.include_router(monitor.router)
    return app


app = create_app()

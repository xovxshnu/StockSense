from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import adjustments, auth, categories, contacts, dashboard, deliveries, health, locations, movements, products, receipts, reorder_rules, stock, transfers, warehouses
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)
    if settings.cors_origins or settings.cors_origin_regex:
        # Auth uses a Bearer header, not cookies, so credentials stay disabled.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_origin_regex=settings.cors_origin_regex,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    # Canonical health routes are under /api (frontend and hosting health checks).
    # The same router is also served at the root so the original /health keeps
    # working; those duplicates are hidden from the OpenAPI schema.
    app.include_router(health.router, prefix="/api")
    app.include_router(health.router, include_in_schema=False)
    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(products.router)
    app.include_router(warehouses.router)
    app.include_router(locations.router)
    app.include_router(contacts.router)
    app.include_router(reorder_rules.router)
    app.include_router(receipts.router)
    app.include_router(deliveries.router)
    app.include_router(transfers.router)
    app.include_router(adjustments.router)
    app.include_router(stock.router)
    app.include_router(movements.router)
    app.include_router(dashboard.router)
    return app


app = create_app()

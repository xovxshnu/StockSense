from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, categories, contacts, health, locations, products, reorder_rules, warehouses
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    if settings.cors_origins:
        # Auth uses a Bearer header, not cookies, so credentials stay disabled.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(products.router)
    app.include_router(warehouses.router)
    app.include_router(locations.router)
    app.include_router(contacts.router)
    app.include_router(reorder_rules.router)
    return app


app = create_app()

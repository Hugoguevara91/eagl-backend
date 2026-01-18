import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.me import router as me_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.clients import router as clients_router
from app.api.v1.bulk import router as bulk_router
from app.api.v1.customer_accounts import router as customer_accounts_router
from app.api.v1.sites import router as sites_router
from app.api.v1.assets import router as assets_router
from app.api.v1.work_orders import router as work_orders_router
from app.api.v1.os_types import router as os_types_router
from app.api.v1.questionnaires import router as questionnaires_router
from app.api.v1.platform import router as platform_router
from app.api.v1.console import router as console_router
from app.api.v1.doctor import router as doctor_router
from app.api.v1.rbac import router as rbac_router
from app.api.v1.users import router as users_router
from app.api.v1.colaboradores import router as colaboradores_router
from app.api.v1.ssma import router as ssma_router
from app.api.v1.orcamentos import router as orcamentos_router
from app.api.v1.suprimentos import router as suprimentos_router
from app.api.v1.map_contracts import router as map_contracts_router
from app.catalog.router import router as catalog_router
from app.solver.router import public_router as solver_public_router
from app.solver.router import router as solver_router
from app.scan.router import router as scan_router
from app.core.config import settings
from app.db import models
from app.db.init_db import ensure_platform_schema, ensure_rbac_defaults, seed_initial_data
from app.db.session import SessionLocal, engine

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("eagl")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Plataforma EAGL - Gestao de Ativos e Manutencao",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    models.Base.metadata.create_all(bind=engine)
    ensure_platform_schema(engine)
    seed_initial_data()
    with SessionLocal() as db:
        ensure_rbac_defaults(db)
    if settings.ENV.lower() == "production":
        if settings.SECRET_KEY == "dev-secret-change-me":
            logger.warning("SECRET_KEY esta usando valor padrao em producao.")
        if settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
            logger.warning("SQLALCHEMY_DATABASE_URI aponta para SQLite em producao.")


app.include_router(auth_router, prefix="/api")
app.include_router(me_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(bulk_router, prefix="/api")
app.include_router(customer_accounts_router, prefix="/api")
app.include_router(sites_router, prefix="/api")
app.include_router(assets_router, prefix="/api")
app.include_router(work_orders_router, prefix="/api")
app.include_router(os_types_router, prefix="/api")
app.include_router(questionnaires_router, prefix="/api")
app.include_router(platform_router, prefix="/api")
app.include_router(console_router, prefix="/api/console")
app.include_router(doctor_router, prefix="/api")
app.include_router(rbac_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(colaboradores_router, prefix="/api")
app.include_router(ssma_router, prefix="/api")
app.include_router(orcamentos_router, prefix="/api")
app.include_router(suprimentos_router, prefix="/api")
app.include_router(map_contracts_router, prefix="/api")
app.include_router(catalog_router, prefix="/api")
app.include_router(solver_router, prefix="/api")
app.include_router(scan_router, prefix="/api")
app.include_router(solver_public_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request method=%s path=%s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}

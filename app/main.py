from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.admin_routes import router as admin_router
from app.api.routes import router
from app.core.config import get_settings
from app.core.observability import correlation_and_logging_middleware
from app.infrastructure.database import engine
from app.modules.platform.api.routes import router as platform_router

settings=get_settings(); app=FastAPI(title=settings.app_name,version="0.2.0")
app.middleware("http")(correlation_and_logging_middleware)
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(router)
app.include_router(admin_router)
app.include_router(platform_router)
@app.get("/health",tags=["operations"])
async def health(): return {"status":"ok","service":settings.app_name}
@app.get("/ready",tags=["operations"])
async def ready():
    try:
        async with engine.connect() as connection: await connection.execute(text("SELECT 1"))
    except Exception: return __import__('fastapi').responses.JSONResponse({"status":"not_ready"},status_code=503)
    return {"status":"ready"}

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.response import ok

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
def healthz() -> dict:
    return ok({"status": "healthy"})


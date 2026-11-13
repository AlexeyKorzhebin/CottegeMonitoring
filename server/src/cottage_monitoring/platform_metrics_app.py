"""Standalone platform-metrics receiver; independent of household application lifespan."""

from fastapi import FastAPI

from cottage_monitoring.api.platform_metrics import router

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(router, prefix="/api/v1")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Process liveness only; this does not assert database readiness."""
    return {"status": "ok"}

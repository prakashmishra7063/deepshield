import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from . import migrate
from .ratelimit import client_ip, limiter
from .routers import admin, analyses, auth, cases, orgs, system
from .worker import jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate.upgrade()
    jobs.start()
    yield
    jobs.stop()


app = FastAPI(
    title="DeepShield AI API",
    version="1.0.0",
    description="Deepfake and manipulated-media analysis. Every result is a probabilistic estimate, not proof.",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$|^extension://[a-p]{32}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Retry-After"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        try:
            limiter.check(f"ip:{client_ip(request)}", get_settings().rate_limit_per_minute * 5, 60)
        except Exception as e:  # HTTPException from limiter
            return JSONResponse({"detail": getattr(e, "detail", "Rate limited")}, status_code=429,
                                headers=getattr(e, "headers", None))
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path != "/docs":
        resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; img-src 'self'; frame-ancestors 'none'")
    return resp


for r in (auth.router, orgs.router, analyses.router, cases.router, system.router, admin.router):
    app.include_router(r, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": "DeepShield AI", "tagline": "See Beyond the Fake. Protect What's Real.", "docs": "/docs"}

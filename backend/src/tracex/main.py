"""FastAPI Application Main Entry Point.
Initializes database, CORS, router endpoints, health checks,
and serves the standalone Prototype UI template.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os

from tracex.settings import settings
from tracex.repositories.db import init_db
from tracex.api.v1.routes import router as api_v1_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="TRACE-X Hackathon V1 MVP: Deterministic Fraud Tracing, Exact Money Conservation, and Separation of Duties.",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware (permits frontend template or external dev servers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup: initialize database tables
@app.on_event("startup")
def on_startup():
    init_db()

# Health endpoints
@app.get("/health/live", tags=["Health"])
def health_live():
    return {"status": "alive"}

@app.get("/health/ready", tags=["Health"])
def health_ready():
    return {
        "status": "ready",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "is_synthetic_demo": settings.IS_SYNTHETIC_DEMO,
    }

# Mount API v1 router
app.include_router(api_v1_router, prefix=settings.API_V1_STR)

# Serve standalone template UI at root "/" and "/template"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "templates", "index.html")

@app.get("/", response_class=HTMLResponse, tags=["Frontend Template"])
@app.get("/template", response_class=HTMLResponse, tags=["Frontend Template"])
def serve_template():
    if os.path.exists(TEMPLATE_PATH):
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TRACE-X Template not found. Check backend/src/tracex/templates/index.html</h1>"

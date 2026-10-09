"""TRACE-X API and frontend application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

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

# Local development frontend. Production build is served same-origin below.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
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

# Serve the independently built React application when available. The historic
# standalone template remains accessible at /template for backend comparison.
FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"

if FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="frontend-assets")

@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
def serve_frontend():
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>TRACE-X frontend build not found. Run the frontend build first.</h1>", status_code=503)


@app.get("/template", response_class=HTMLResponse, tags=["Legacy Frontend Reference"])
def serve_template():
    if TEMPLATE_PATH.exists():
        with TEMPLATE_PATH.open("r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TRACE-X Template not found. Check backend/src/tracex/templates/index.html</h1>"

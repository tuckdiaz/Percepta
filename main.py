import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import init_db
from services.scheduler_service import start_scheduler, shutdown_scheduler, reload_scheduler_jobs
from routes.auth import router as auth_router
from routes.cameras import router as cameras_router
from routes.storage import router as storage_router
from routes.settings import router as settings_router
from routes.system import router as system_router

# Setup centralized logging to console and to storage disk
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/storage")
LOG_DIR = os.path.join(STORAGE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "percepta.log")

log_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# Rotating File Handler on storage disk (Max 10 MB per file, 5 backups)
try:
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
except Exception as log_err:
    print(f"Warning: Could not open log file at {LOG_FILE}: {log_err}")

logger = logging.getLogger("percepta.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("==========================================")
    logger.info("Starting Percepta Tapo CCTV System...")
    logger.info(f"Storage Root: {STORAGE_DIR}")
    logger.info(f"Log Destination: {LOG_FILE}")
    logger.info("==========================================")

    # 1. Initialize SQLite Database schema & seeds
    await init_db()
    logger.info("Database initialized.")

    # 2. Start Background Scheduler
    start_scheduler()
    await reload_scheduler_jobs()
    logger.info("Background scheduler initialized.")

    yield

    # Shutdown
    shutdown_scheduler()
    logger.info("Percepta shutdown complete.")

app = FastAPI(
    title="Percepta Tapo CCTV Manager",
    description="Automated Footage Downloader, Storage Lifecycle & Monitoring GUI",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router)
app.include_router(cameras_router)
app.include_router(storage_router)
app.include_router(settings_router)
app.include_router(system_router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Frontend Static Files
FRONTEND_DIR = os.environ.get("FRONTEND_DIR", "/app/frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        # Serve frontend files if they exist, else index.html
        fp = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

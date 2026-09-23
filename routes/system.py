import os
import psutil
import time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, Setting, get_db
from routes.auth import get_current_user
from services.storage_service import get_storage_path, get_disk_stats
from services.camera_service import sync_status

router = APIRouter(prefix="/api/system", tags=["system"])
START_TIME = time.time()

@router.get("/stats")
async def get_system_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    base_storage = await get_storage_path()
    disk_stats = get_disk_stats(base_storage)
    
    # RAM and CPU
    vm = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=None)

    # Get configured RAM limit
    res = await db.execute(select(Setting).where(Setting.key == "ram_limit_pct"))
    ram_setting = res.scalar_one_or_none()
    ram_limit = float(ram_setting.value) if ram_setting else 90.0

    uptime_sec = int(time.time() - START_TIME)

    return {
        "cpu_percent": cpu_pct,
        "ram": {
            "total_mb": round(vm.total / (1024 * 1024), 1),
            "used_mb": round(vm.used / (1024 * 1024), 1),
            "free_mb": round(vm.available / (1024 * 1024), 1),
            "used_percent": round(vm.percent, 1),
            "limit_percent": ram_limit,
            "status": "normal" if vm.percent < ram_limit else "throttled"
        },
        "disk": disk_stats,
        "uptime_seconds": uptime_sec,
        "sync_status": sync_status
    }

@router.get("/logs")
async def get_system_logs(
    lines: int = Query(100, ge=10, le=1000),
    level: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    base_storage = await get_storage_path()
    log_file = os.path.join(base_storage, "logs", "percepta.log")

    if not os.path.isfile(log_file):
        return {"logs": [], "log_file": log_file, "message": "No log file found yet."}

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        if level:
            filtered = [l for l in all_lines if level.upper() in l]
        else:
            filtered = all_lines

        tail_lines = [l.strip() for l in filtered[-lines:]]
        return {
            "logs": tail_lines,
            "log_file": log_file,
            "total_lines": len(tail_lines)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")

@router.delete("/logs")
async def clear_system_logs(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can clear logs.")

    base_storage = await get_storage_path()
    log_file = os.path.join(base_storage, "logs", "percepta.log")

    if os.path.isfile(log_file):
        with open(log_file, "w") as f:
            f.write("")

    return {"success": True, "message": "Logs cleared."}

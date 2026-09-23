from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import Setting, User, get_db
from routes.auth import get_current_user
from services.scheduler_service import reload_scheduler_jobs
from services.github_service import perform_github_backup

router = APIRouter(prefix="/api/settings", tags=["settings"])

class SettingsUpdate(BaseModel):
    storage_path: str
    schedule_time: str
    schedule_enabled: bool
    schedule_mode: str  # daily or interval
    schedule_interval_hours: int
    ram_limit_pct: int
    retention_days: int
    weekly_zip_enabled: bool
    weekly_zip_day: int
    github_repo_url: str
    github_token: str
    github_branch: str
    github_backup_enabled: bool

@router.get("")
async def get_all_settings(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Setting))
    settings_dict = {s.key: s.value for s in res.scalars().all()}
    
    # Hide raw token in display
    raw_token = settings_dict.get("github_token", "")
    masked_token = (raw_token[:4] + "..." + raw_token[-4:]) if len(raw_token) > 8 else ("***" if raw_token else "")

    return {
        "storage_path": settings_dict.get("storage_path", "/storage"),
        "schedule_time": settings_dict.get("schedule_time", "02:00"),
        "schedule_enabled": settings_dict.get("schedule_enabled", "true") == "true",
        "schedule_mode": settings_dict.get("schedule_mode", "daily"),
        "schedule_interval_hours": int(settings_dict.get("schedule_interval_hours", "6")),
        "ram_limit_pct": int(settings_dict.get("ram_limit_pct", "90")),
        "retention_days": int(settings_dict.get("retention_days", "30")),
        "weekly_zip_enabled": settings_dict.get("weekly_zip_enabled", "true") == "true",
        "weekly_zip_day": int(settings_dict.get("weekly_zip_day", "6")),
        "github_repo_url": settings_dict.get("github_repo_url", ""),
        "github_token": masked_token,
        "has_github_token": bool(raw_token),
        "github_branch": settings_dict.get("github_branch", "main"),
        "github_backup_enabled": settings_dict.get("github_backup_enabled", "true") == "true",
        "last_github_backup": settings_dict.get("last_github_backup", ""),
        "last_weekly_archive": settings_dict.get("last_weekly_archive", "")
    }

@router.post("")
async def update_settings(req: SettingsUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update system settings.")

    updates = {
        "storage_path": req.storage_path.strip(),
        "schedule_time": req.schedule_time.strip(),
        "schedule_enabled": "true" if req.schedule_enabled else "false",
        "schedule_mode": req.schedule_mode,
        "schedule_interval_hours": str(req.schedule_interval_hours),
        "ram_limit_pct": str(req.ram_limit_pct),
        "retention_days": str(req.retention_days),
        "weekly_zip_enabled": "true" if req.weekly_zip_enabled else "false",
        "weekly_zip_day": str(req.weekly_zip_day),
        "github_repo_url": req.github_repo_url.strip(),
        "github_branch": req.github_branch.strip() or "main",
        "github_backup_enabled": "true" if req.github_backup_enabled else "false"
    }

    # Only update token if a new non-masked value is provided
    if req.github_token and "..." not in req.github_token and "***" not in req.github_token:
        updates["github_token"] = req.github_token.strip()

    for k, v in updates.items():
        res = await db.execute(select(Setting).where(Setting.key == k))
        setting = res.scalar_one_or_none()
        if setting:
            setting.value = v
        else:
            db.add(Setting(key=k, value=v))

    await db.commit()

    # Dynamic scheduler reload
    await reload_scheduler_jobs()

    return {"success": True, "message": "Settings updated successfully."}

@router.post("/github/backup-now")
async def trigger_github_backup(current_user: User = Depends(get_current_user)):
    res = await perform_github_backup()
    return res

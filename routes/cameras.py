import asyncio
from datetime import datetime, date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Camera, User, get_db
from routes.auth import get_current_user
from services.camera_service import (
    test_camera_connection,
    sync_single_camera,
    sync_all_cameras,
    sync_status,
    sync_lock
)

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

class CameraCreate(BaseModel):
    name: str
    ip: str
    cloud_password: str
    user: Optional[str] = "admin"
    password: Optional[str] = ""
    window_size: Optional[int] = 50
    enabled: Optional[bool] = True

class CameraUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    cloud_password: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    window_size: Optional[int] = None
    enabled: Optional[bool] = None

class CameraOut(BaseModel):
    id: int
    name: str
    ip: str
    user: str
    window_size: int
    enabled: bool
    last_sync: Optional[datetime] = None
    last_status: str
    created_at: datetime

    class Config:
        from_attributes = True

class TestConnRequest(BaseModel):
    ip: str
    cloud_password: str
    user: Optional[str] = "admin"
    password: Optional[str] = ""

class SyncDateRequest(BaseModel):
    date_str: Optional[str] = None  # Format: YYYY-MM-DD

@router.get("", response_model=List[CameraOut])
async def list_cameras(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Camera))
    return res.scalars().all()

@router.post("", response_model=CameraOut)
async def add_camera(cam_in: CameraCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Check duplicate name
    res = await db.execute(select(Camera).where(Camera.name == cam_in.name))
    if res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Camera with this name already exists.")

    new_cam = Camera(
        name=cam_in.name.strip(),
        ip=cam_in.ip.strip(),
        cloud_password=cam_in.cloud_password.strip(),
        user=cam_in.user.strip() if cam_in.user else "admin",
        password=cam_in.password.strip() if cam_in.password else "",
        window_size=cam_in.window_size or 50,
        enabled=cam_in.enabled if cam_in.enabled is not None else True,
        last_status="idle"
    )
    db.add(new_cam)
    await db.commit()
    await db.refresh(new_cam)
    return new_cam

@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: int, cam_in: CameraUpdate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam = res.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found.")

    if cam_in.name is not None:
        cam.name = cam_in.name.strip()
    if cam_in.ip is not None:
        cam.ip = cam_in.ip.strip()
    if cam_in.cloud_password is not None and cam_in.cloud_password.strip() != "":
        cam.cloud_password = cam_in.cloud_password.strip()
    if cam_in.user is not None:
        cam.user = cam_in.user.strip()
    if cam_in.password is not None and cam_in.password.strip() != "":
        cam.password = cam_in.password.strip()
    if cam_in.window_size is not None:
        cam.window_size = cam_in.window_size
    if cam_in.enabled is not None:
        cam.enabled = cam_in.enabled

    await db.commit()
    await db.refresh(cam)
    return cam

@router.delete("/{camera_id}")
async def delete_camera(camera_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Camera).where(Camera.id == camera_id))
    cam = res.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found.")

    await db.delete(cam)
    await db.commit()
    return {"success": True, "message": f"Camera '{cam.name}' deleted."}

@router.post("/test")
async def test_connection(req: TestConnRequest, current_user: User = Depends(get_current_user)):
    res = await test_camera_connection(
        ip=req.ip.strip(),
        cloud_password=req.cloud_password.strip(),
        user=req.user.strip() if req.user else "admin",
        password=req.password.strip() if req.password else ""
    )
    return res

@router.get("/sync-status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    return sync_status

@router.post("/{camera_id}/sync")
async def trigger_camera_sync(
    camera_id: int,
    req: Optional[SyncDateRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if sync_lock.locked():
        raise HTTPException(status_code=409, detail="A sync job is already in progress.")

    target_d = None
    if req and req.date_str:
        try:
            target_d = datetime.strptime(req.date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    background_tasks.add_task(sync_single_camera, camera_id, target_d)
    return {"success": True, "message": "Camera sync started in background."}

@router.post("/sync-all")
async def trigger_all_sync(
    req: Optional[SyncDateRequest] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_user)
):
    if sync_lock.locked():
        raise HTTPException(status_code=409, detail="A sync job is already in progress.")

    target_d = None
    if req and req.date_str:
        try:
            target_d = datetime.strptime(req.date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    background_tasks.add_task(sync_all_cameras, target_d)
    return {"success": True, "message": "Sequential sync for all cameras started in background."}

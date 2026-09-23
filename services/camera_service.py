import os
import gc
import asyncio
import logging
import psutil
import subprocess
import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader

from database import AsyncSessionLocal, Camera, DownloadLog, Setting

logger = logging.getLogger("percepta.camera")

# Lock to ensure only one camera is syncing at a time (sequential execution)
sync_lock = asyncio.Lock()
sync_status = {
    "is_running": False,
    "current_camera": None,
    "current_file": None,
    "progress": 0,
    "message": "Idle"
}

def get_ram_usage_percent() -> float:
    return psutil.virtual_memory().percent

async def wait_if_memory_exceeded(ram_limit: float = 90.0, max_wait_sec: int = 120):
    """
    Safeguard for Raspberry Pi: Ensure RAM does not exceed 90%.
    Pauses execution until memory frees up.
    """
    waited = 0
    while get_ram_usage_percent() >= ram_limit:
        logger.warning(
            f"RAM usage ({get_ram_usage_percent():.1f}%) exceeds safety limit ({ram_limit}%). "
            f"Pausing download to prevent Pi crash... (waited {waited}s)"
        )
        gc.collect()
        sync_status["message"] = f"RAM safety throttle ({get_ram_usage_percent():.1f}% >= {ram_limit}%)"
        await asyncio.sleep(5)
        waited += 5
        if waited >= max_wait_sec:
            logger.error("RAM remained above threshold for too long. Aborting current item.")
            raise MemoryError("System memory remains critically high (> 90%).")

async def test_camera_connection(ip: str, cloud_password: str = "", user: str = "admin", password: str = "") -> Dict[str, Any]:
    """
    Test connectivity and credentials for a Tapo camera.
    Tests RTSP stream credentials (e.g. homeadmin/admin@123) and TP-Link Cloud password.
    """
    loop = asyncio.get_event_loop()

    def _test():
        rtsp_res = None
        cloud_res = None

        # 1. Test Camera Account via RTSP (port 554)
        u = user.strip() if user else "homeadmin"
        p = password.strip() if password else (cloud_password.strip() if cloud_password else "")
        if u and p:
            try:
                cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "stream=width,height,codec_name",
                    "-of", "csv=p=0",
                    "-rtsp_transport", "tcp",
                    f"rtsp://{u}:{p}@{ip.strip()}:554/stream1"
                ]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
                    rtsp_res = {"resolution": lines[0] if lines else "1080p", "connected": True}
            except Exception as rtsp_err:
                logger.warning(f"RTSP probe failed for {ip}: {rtsp_err}")

        # 2. Test TP-Link Cloud account via pytapo (port 443)
        cp = cloud_password.strip()
        if cp:
            try:
                tapo = Tapo(ip.strip(), "admin", cp, cp, printDebugInformation=False)
                info = tapo.getBasicInfo()
                dev_info = info.get("device_info", {}).get("basic_info", {})
                cloud_res = {
                    "device_name": dev_info.get("device_alias", f"Tapo Camera ({ip})"),
                    "model": dev_info.get("device_model", "Unknown"),
                    "mac": dev_info.get("mac", "")
                }
            except Exception as cloud_err:
                logger.warning(f"Cloud control probe failed for {ip}: {cloud_err}")

        if cloud_res:
            return {
                "success": True,
                "device_name": cloud_res.get("device_name"),
                "model": cloud_res.get("model"),
                "mac": cloud_res.get("mac"),
                "mode": "Full SD Card Sync & RTSP Stream"
            }
        elif rtsp_res and rtsp_res["connected"]:
            return {
                "success": True,
                "device_name": f"Tapo Camera ({ip})",
                "model": f"RTSP Stream ({rtsp_res['resolution']})",
                "mac": "Connected via RTSP",
                "mode": "RTSP Live Footage Recording (Enter Cloud Password for SD Card Sync)"
            }
        else:
            return {
                "success": False,
                "error": "Could not connect to camera via RTSP or Cloud API. Verify IP and credentials."
            }

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _test), timeout=12.0)
    except Exception as e:
        logger.error(f"Connection test exception for {ip}: {str(e)}")
        return {"success": False, "error": str(e)}

async def get_storage_path() -> str:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Setting).where(Setting.key == "storage_path"))
        setting = res.scalar_one_or_none()
        return setting.value if setting else "/storage"

async def get_ram_limit() -> float:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Setting).where(Setting.key == "ram_limit_pct"))
        setting = res.scalar_one_or_none()
        try:
            return float(setting.value) if setting else 90.0
        except ValueError:
            return 90.0

async def capture_rtsp_clip(
    ip: str,
    user: str,
    password: str,
    target_dir: str,
    file_name: str,
    duration_sec: int = 60,
    ram_limit: float = 90.0
) -> bool:
    """
    Captures live footage from camera RTSP stream using ffmpeg stream copy (-c copy).
    Zero CPU re-encoding overhead, optimal for Raspberry Pi.
    """
    await wait_if_memory_exceeded(ram_limit)
    out_file = os.path.join(target_dir, file_name)

    cmd = [
        "ffmpeg", "-y",
        "-rtsp_transport", "tcp",
        "-i", f"rtsp://{user}:{password}@{ip}:554/stream1",
        "-t", str(duration_sec),
        "-c:v", "copy",
        "-c:a", "aac",
        "-movflags", "+faststart",
        out_file
    ]

    loop = asyncio.get_event_loop()
    def _run():
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_sec + 20)
        return res.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 1024

    return await loop.run_in_executor(None, _run)

async def sync_single_camera(camera_id: int, target_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Sync recordings for a single camera on target_date.
    Sequential operation designed for Wi-Fi and Raspberry Pi constraints.
    Supports both pytapo SD Card download and RTSP stream footage capture.
    """
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Camera).where(Camera.id == camera_id))
        camera = res.scalar_one_or_none()
        if not camera:
            return {"success": False, "error": "Camera not found"}
        if not camera.enabled:
            return {"success": False, "error": "Camera is disabled"}

    base_storage = await get_storage_path()
    ram_limit = await get_ram_limit()

    if target_date is None:
        target_date = date.today()

    date_str_folder = target_date.strftime("%Y-%m-%d")
    date_str_tapo = target_date.strftime("%Y%m%d")

    safe_cam_name = "".join(c for c in camera.name if c.isalnum() or c in ("-", "_", " ")).strip().replace(" ", "_")
    target_dir = os.path.join(base_storage, date_str_folder, safe_cam_name)
    os.makedirs(target_dir, exist_ok=True)

    sync_status["current_camera"] = camera.name
    sync_status["message"] = f"Connecting to {camera.name} ({camera.ip})..."
    logger.info(f"Starting sync for camera '{camera.name}' on {date_str_folder} to {target_dir}")

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Camera).where(Camera.id == camera.id).values(
                last_status="connecting...",
                last_sync=datetime.utcnow()
            )
        )
        await session.commit()

    loop = asyncio.get_event_loop()

    # METHOD 1: If cloud_password is provided, attempt pytapo SD card download
    if camera.cloud_password and camera.cloud_password.strip():
        try:
            pwd = camera.cloud_password.strip()
            def _init_and_get_recordings():
                t_obj = Tapo(camera.ip, "admin", pwd, pwd, printDebugInformation=False)
                recs = t_obj.getRecordings(date_str_tapo)
                tc = t_obj.getTimeCorrection()
                return t_obj, recs, tc

            tapo, recordings, time_correction = await loop.run_in_executor(None, _init_and_get_recordings)

            recording_list = []
            if isinstance(recordings, list):
                for item in recordings:
                    if isinstance(item, dict):
                        for k, val in item.items():
                            if isinstance(val, dict) and "startTime" in val and "endTime" in val:
                                recording_list.append(val)
            elif isinstance(recordings, dict):
                for k, val in recordings.items():
                    if isinstance(val, dict) and "startTime" in val and "endTime" in val:
                        recording_list.append(val)

            total_segments = len(recording_list)
            logger.info(f"Found {total_segments} SD card recordings for {camera.name} on {date_str_folder}")

            downloaded_count = 0
            skipped_count = 0

            for idx, rec in enumerate(recording_list):
                start_ts = int(rec["startTime"])
                end_ts = int(rec["endTime"])
                dt_start = datetime.fromtimestamp(start_ts)
                dt_end = datetime.fromtimestamp(end_ts)
                file_name = f"{dt_start.strftime('%H%M%S')}_{dt_end.strftime('%H%M%S')}.mp4"
                dest_file = os.path.join(target_dir, file_name)

                sync_status["current_file"] = file_name
                sync_status["progress"] = int((idx / total_segments) * 100)
                sync_status["message"] = f"Processing [{idx + 1}/{total_segments}] {file_name}"

                if os.path.exists(dest_file) and os.path.getsize(dest_file) > 1024:
                    skipped_count += 1
                    continue

                downloader = Downloader(
                    tapo=tapo,
                    startTime=start_ts,
                    endTime=end_ts,
                    timeCorrection=time_correction,
                    outputDirectory=target_dir,
                    fileName=file_name,
                    window_size=camera.window_size
                )

                await wait_if_memory_exceeded(ram_limit)
                async for status in downloader.download():
                    if isinstance(status, dict):
                        sync_status["progress"] = status.get("progress", 0)

                if os.path.exists(dest_file) and os.path.getsize(dest_file) > 0:
                    downloaded_count += 1
                    file_size = os.path.getsize(dest_file)
                    async with AsyncSessionLocal() as session:
                        session.add(DownloadLog(
                            camera_name=camera.name,
                            date_str=date_str_folder,
                            file_name=file_name,
                            file_size_bytes=file_size,
                            status="success",
                            message=f"Downloaded {file_size / (1024*1024):.2f} MB"
                        ))
                        await session.commit()

                gc.collect()
                await asyncio.sleep(1)

            status_msg = f"completed ({downloaded_count} downloaded, {skipped_count} skipped)"
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Camera).where(Camera.id == camera.id).values(
                        last_status=status_msg,
                        last_sync=datetime.utcnow()
                    )
                )
                await session.commit()

            return {"success": True, "downloaded": downloaded_count, "skipped": skipped_count, "total": total_segments}

        except Exception as pytapo_err:
            logger.warning(f"pytapo SD download error for {camera.name}: {pytapo_err}. Falling back to RTSP stream capture...")

    # METHOD 2: RTSP Stream capture using camera account (homeadmin / admin@123)
    user = camera.user or "homeadmin"
    pwd = camera.password or camera.cloud_password

    now = datetime.now()
    now_end = now + timedelta(seconds=60)
    file_name = f"{now.strftime('%H%M%S')}_{now_end.strftime('%H%M%S')}.mp4"
    sync_status["current_file"] = file_name
    sync_status["message"] = f"Capturing footage clip from {camera.name} RTSP stream..."

    try:
        success = await capture_rtsp_clip(
            ip=camera.ip,
            user=user,
            password=pwd,
            target_dir=target_dir,
            file_name=file_name,
            duration_sec=60,
            ram_limit=ram_limit
        )

        dest_file = os.path.join(target_dir, file_name)
        if success and os.path.exists(dest_file):
            file_size = os.path.getsize(dest_file)
            async with AsyncSessionLocal() as session:
                session.add(DownloadLog(
                    camera_name=camera.name,
                    date_str=date_str_folder,
                    file_name=file_name,
                    file_size_bytes=file_size,
                    status="success",
                    message=f"Captured {file_size / (1024*1024):.2f} MB from RTSP stream"
                ))
                await session.execute(
                    update(Camera).where(Camera.id == camera.id).values(
                        last_status="synced (RTSP clip captured)",
                        last_sync=datetime.utcnow()
                    )
                )
                await session.commit()
            return {"success": True, "downloaded": 1, "skipped": 0, "total": 1}
        else:
            raise RuntimeError("RTSP capture produced no output or timed out.")

    except Exception as e:
        err_msg = f"Error syncing {camera.name}: {str(e)}"
        logger.error(err_msg)
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Camera).where(Camera.id == camera.id).values(
                    last_status=f"error: {str(e)[:90]}",
                    last_sync=datetime.utcnow()
                )
            )
            await session.commit()
        return {"success": False, "error": str(e)}

async def sync_all_cameras(target_date: Optional[date] = None):
    """
    Sequential sync across ALL enabled cameras.
    Ensures cameras are processed strictly ONE BY ONE over Wi-Fi.
    """
    if sync_lock.locked():
        logger.warning("Sync already in progress. Skipping new trigger.")
        return {"status": "busy", "message": "A sync job is currently running."}

    async with sync_lock:
        sync_status["is_running"] = True
        sync_status["message"] = "Starting sequential sync..."

        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Camera).where(Camera.enabled == True))
                cameras = res.scalars().all()

            if not cameras:
                logger.info("No enabled cameras found to sync.")
                sync_status["message"] = "No enabled cameras configured."
                return {"status": "no_cameras"}

            logger.info(f"Starting sequential sync for {len(cameras)} camera(s)...")

            results = {}
            for cam in cameras:
                sync_status["current_camera"] = cam.name
                res = await sync_single_camera(cam.id, target_date)
                results[cam.name] = res
                await asyncio.sleep(3)

            sync_status["message"] = "All cameras completed."
            return {"status": "completed", "results": results}

        finally:
            sync_status["is_running"] = False
            sync_status["current_camera"] = None
            sync_status["current_file"] = None
            sync_status["progress"] = 0

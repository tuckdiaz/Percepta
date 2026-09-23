import os
import shutil
import zipfile
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select

from database import AsyncSessionLocal, Setting

logger = logging.getLogger("percepta.storage")

def get_disk_stats(path: str) -> Dict[str, Any]:
    """
    Get total, used, free bytes and percentage for the given path.
    """
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        usage = shutil.disk_usage(path)
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 1),
            "free_percent": round((usage.free / usage.total) * 100, 1),
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2)
        }
    except Exception as e:
        logger.error(f"Error calculating disk usage for {path}: {str(e)}")
        return {
            "total_bytes": 0, "used_bytes": 0, "free_bytes": 0,
            "used_percent": 0, "free_percent": 0, "total_gb": 0,
            "used_gb": 0, "free_gb": 0, "error": str(e)
        }

async def get_storage_path() -> str:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Setting).where(Setting.key == "storage_path"))
        setting = res.scalar_one_or_none()
        return setting.value if setting else "/storage"

def scan_footage_tree(base_storage: str) -> List[Dict[str, Any]]:
    """
    Scans {base_storage}/{YYYY-MM-DD}/{camera_name}/*.mp4
    Returns structured data for the Web GUI recordings explorer.
    """
    if not os.path.exists(base_storage):
        return []

    date_entries = []

    # Filter directories that match YYYY-MM-DD
    for item in sorted(os.listdir(base_storage), reverse=True):
        date_dir = os.path.join(base_storage, item)
        if not os.path.isdir(date_dir) or item in ("logs", "archives", "temp"):
            continue

        # Check if item matches YYYY-MM-DD pattern
        is_date = False
        try:
            datetime.strptime(item, "%Y-%m-%d")
            is_date = True
        except ValueError:
            pass

        if not is_date:
            continue

        cameras_list = []
        total_date_size = 0
        total_date_files = 0

        for cam_name in sorted(os.listdir(date_dir)):
            cam_dir = os.path.join(date_dir, cam_name)
            if not os.path.isdir(cam_dir):
                continue

            files_list = []
            cam_size = 0

            for f in sorted(os.listdir(cam_dir)):
                if not f.lower().endswith((".mp4", ".ts", ".mkv")):
                    continue
                file_path = os.path.join(cam_dir, f)
                file_size = os.path.getsize(file_path)
                cam_size += file_size

                # Format human readable time label from filename like 091500_092000.mp4
                time_label = f
                parts = f.replace(".mp4", "").split("_")
                if len(parts) == 2 and len(parts[0]) == 6 and len(parts[1]) == 6:
                    t1 = f"{parts[0][:2]}:{parts[0][2:4]}:{parts[0][4:]}"
                    t2 = f"{parts[1][:2]}:{parts[1][2:4]}:{parts[1][4:]}"
                    time_label = f"{t1} - {t2}"

                files_list.append({
                    "name": f,
                    "relative_path": f"{item}/{cam_name}/{f}",
                    "size_bytes": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "time_label": time_label
                })

            if files_list:
                total_date_size += cam_size
                total_date_files += len(files_list)
                cameras_list.append({
                    "name": cam_name,
                    "total_files": len(files_list),
                    "total_size_mb": round(cam_size / (1024 * 1024), 2),
                    "files": files_list
                })

        if cameras_list:
            date_entries.append({
                "date": item,
                "total_files": total_date_files,
                "total_size_mb": round(total_date_size / (1024 * 1024), 2),
                "cameras": cameras_list
            })

    return date_entries

def scan_archives_list(base_storage: str) -> List[Dict[str, Any]]:
    """
    Returns list of weekly zip archives in {base_storage}/archives.
    """
    archives_dir = os.path.join(base_storage, "archives")
    if not os.path.exists(archives_dir):
        return []

    archives = []
    for f in sorted(os.listdir(archives_dir), reverse=True):
        if f.lower().endswith(".zip"):
            p = os.path.join(archives_dir, f)
            size = os.path.getsize(p)
            archives.append({
                "name": f,
                "relative_path": f"archives/{f}",
                "size_mb": round(size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")
            })
    return archives

async def perform_weekly_archive(days_back: int = 7) -> Dict[str, Any]:
    """
    End-of-week task:
    Finds footage folders older than 7 days, compresses each completed week into a ZIP archive,
    and removes raw video files once verified.
    """
    base_storage = await get_storage_path()
    archives_dir = os.path.join(base_storage, "archives")
    os.makedirs(archives_dir, exist_ok=True)

    today = date.today()
    cutoff_date = today - timedelta(days=days_back)
    logger.info(f"Running weekly archive job for footage older than {cutoff_date}...")

    archived_count = 0
    errors = []

    for item in os.listdir(base_storage):
        date_path = os.path.join(base_storage, item)
        if not os.path.isdir(date_path) or item in ("logs", "archives", "temp"):
            continue

        try:
            folder_date = datetime.strptime(item, "%Y-%m-%d").date()
        except ValueError:
            continue

        # Archive if older than 7 days
        if folder_date <= cutoff_date:
            zip_filename = f"footage_{item}.zip"
            zip_dest = os.path.join(archives_dir, zip_filename)

            if os.path.exists(zip_dest):
                logger.info(f"Archive {zip_filename} already exists. Skipping compression.")
                continue

            logger.info(f"Creating archive for {item} -> {zip_filename}...")
            try:
                temp_zip = zip_dest + ".tmp"
                with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for root, _, files in os.walk(date_path):
                        for file in files:
                            if file.lower().endswith((".mp4", ".ts")):
                                full_p = os.path.join(root, file)
                                rel_p = os.path.relpath(full_p, date_path)
                                zipf.write(full_p, arcname=os.path.join(item, rel_p))

                # Verify zip integrity
                with zipfile.ZipFile(temp_zip, "r") as zipf:
                    test_res = zipf.testzip()
                    if test_res is not None:
                        raise ValueError(f"Corrupt zip archive created for {item}: {test_res}")

                # Rename tmp to final
                os.replace(temp_zip, zip_dest)
                logger.info(f"Successfully archived {item} to {zip_filename}. Cleaning raw files...")

                # Remove raw date directory to reclaim disk space
                shutil.rmtree(date_path, ignore_errors=True)
                archived_count += 1

            except Exception as e:
                logger.error(f"Failed to archive {item}: {str(e)}")
                errors.append(f"{item}: {str(e)}")
                if os.path.exists(temp_zip):
                    try:
                        os.remove(temp_zip)
                    except OSError:
                        pass

    return {
        "success": len(errors) == 0,
        "archived_folders": archived_count,
        "errors": errors
    }

async def perform_retention_cleanup(retention_days: int = 30) -> Dict[str, Any]:
    """
    Deletes footage and zip archives older than retention_days (default 30 days / 1 month).
    """
    base_storage = await get_storage_path()
    today = date.today()
    cutoff_date = today - timedelta(days=retention_days)
    logger.info(f"Purging footages and archives older than {cutoff_date} ({retention_days} days)...")

    deleted_count = 0

    # Clean raw date directories
    if os.path.exists(base_storage):
        for item in os.listdir(base_storage):
            date_path = os.path.join(base_storage, item)
            if not os.path.isdir(date_path) or item in ("logs", "archives", "temp"):
                continue

            try:
                folder_date = datetime.strptime(item, "%Y-%m-%d").date()
                if folder_date < cutoff_date:
                    logger.info(f"Retention policy: Deleting old footage folder {item}")
                    shutil.rmtree(date_path, ignore_errors=True)
                    deleted_count += 1
            except ValueError:
                continue

    # Clean archives folder
    archives_dir = os.path.join(base_storage, "archives")
    if os.path.exists(archives_dir):
        for item in os.listdir(archives_dir):
            if not item.endswith(".zip"):
                continue
            archive_path = os.path.join(archives_dir, item)
            try:
                # Check modification time
                mtime = datetime.fromtimestamp(os.path.getmtime(archive_path)).date()
                if mtime < cutoff_date:
                    logger.info(f"Retention policy: Deleting old archive {item}")
                    os.remove(archive_path)
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Error checking archive {item}: {str(e)}")

    return {"deleted_items": deleted_count, "cutoff_date": str(cutoff_date)}

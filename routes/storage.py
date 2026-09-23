import os
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from database import User
from routes.auth import get_current_user
from services.storage_service import (
    get_storage_path,
    get_disk_stats,
    scan_footage_tree,
    scan_archives_list,
    perform_weekly_archive,
    perform_retention_cleanup
)

router = APIRouter(prefix="/api/storage", tags=["storage"])

def parse_range_header(range_header: str, file_size: int):
    """
    Parses 'bytes=start-end' Range header for HTML5 video seeking.
    """
    if not range_header or "=" not in range_header:
        return 0, file_size - 1

    unit, ranges = range_header.split("=", 1)
    if unit.strip().lower() != "bytes":
        return 0, file_size - 1

    parts = ranges.split("-")
    start = int(parts[0]) if parts[0] else 0
    end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

    if start >= file_size:
        start = file_size - 1
    if end >= file_size:
        end = file_size - 1
    if start > end:
        start = end

    return start, end

@router.get("/stats")
async def get_storage_statistics(current_user: User = Depends(get_current_user)):
    base_storage = await get_storage_path()
    disk_info = get_disk_stats(base_storage)
    return {
        "storage_path": base_storage,
        "disk": disk_info
    }

@router.get("/browse")
async def browse_recordings(current_user: User = Depends(get_current_user)):
    base_storage = await get_storage_path()
    tree = scan_footage_tree(base_storage)
    archives = scan_archives_list(base_storage)
    return {
        "tree": tree,
        "archives": archives
    }

@router.get("/stream/{date_str}/{camera_name}/{filename}")
async def stream_video(
    date_str: str,
    camera_name: str,
    filename: str,
    request: Request,
    range: Optional[str] = Header(None)
):
    """
    Streams MP4 video with HTTP 206 Partial Content support for HTML5 timeline seeking.
    """
    base_storage = await get_storage_path()
    # Path traversal protection
    clean_date = os.path.basename(date_str)
    clean_cam = os.path.basename(camera_name)
    clean_file = os.path.basename(filename)

    file_path = os.path.join(base_storage, clean_date, clean_cam, clean_file)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Video file not found.")

    file_size = os.path.getsize(file_path)

    if range:
        start, end = parse_range_header(range, file_size)
        content_length = (end - start) + 1

        def iter_chunks():
            chunk_size = 1024 * 512  # 512 KB chunks for smooth playback
            with open(file_path, "rb") as f:
                f.seek(start)
                bytes_left = content_length
                while bytes_left > 0:
                    read_len = min(chunk_size, bytes_left)
                    data = f.read(read_len)
                    if not data:
                        break
                    bytes_left -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Type": "video/mp4",
        }
        return StreamingResponse(iter_chunks(), status_code=206, headers=headers)
    else:
        return FileResponse(file_path, media_type="video/mp4", filename=clean_file)

@router.get("/download/{date_str}/{camera_name}/{filename}")
async def download_video(
    date_str: str,
    camera_name: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    base_storage = await get_storage_path()
    clean_date = os.path.basename(date_str)
    clean_cam = os.path.basename(camera_name)
    clean_file = os.path.basename(filename)

    file_path = os.path.join(base_storage, clean_date, clean_cam, clean_file)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    return FileResponse(file_path, media_type="application/octet-stream", filename=clean_file)

@router.get("/archive/download/{archive_name}")
async def download_archive(
    archive_name: str,
    current_user: User = Depends(get_current_user)
):
    base_storage = await get_storage_path()
    clean_name = os.path.basename(archive_name)
    file_path = os.path.join(base_storage, "archives", clean_name)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Archive not found.")

    return FileResponse(file_path, media_type="application/zip", filename=clean_name)

@router.delete("/file/{date_str}/{camera_name}/{filename}")
async def delete_video_file(
    date_str: str,
    camera_name: str,
    filename: str,
    current_user: User = Depends(get_current_user)
):
    base_storage = await get_storage_path()
    clean_date = os.path.basename(date_str)
    clean_cam = os.path.basename(camera_name)
    clean_file = os.path.basename(filename)

    file_path = os.path.join(base_storage, clean_date, clean_cam, clean_file)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    os.remove(file_path)
    return {"success": True, "message": f"Deleted {clean_file}"}

@router.post("/trigger-archive")
async def trigger_archive_now(current_user: User = Depends(get_current_user)):
    res = await perform_weekly_archive(days_back=7)
    return res

@router.post("/trigger-cleanup")
async def trigger_cleanup_now(current_user: User = Depends(get_current_user)):
    res = await perform_retention_cleanup(retention_days=30)
    return res

import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from database import AsyncSessionLocal, Setting
from services.camera_service import sync_all_cameras
from services.storage_service import perform_weekly_archive, perform_retention_cleanup
from services.github_service import perform_github_backup

logger = logging.getLogger("percepta.scheduler")
scheduler = AsyncIOScheduler()

async def scheduled_footage_sync():
    logger.info("Scheduler triggered: Starting daily CCTV footage sync...")
    try:
        await sync_all_cameras()
    except Exception as e:
        logger.error(f"Scheduled footage sync failed: {str(e)}")

async def scheduled_weekly_maintenance():
    logger.info("Scheduler triggered: Weekly archive & storage retention cleanup...")
    try:
        # Check settings
        async with AsyncSessionLocal() as session:
            zip_setting = (await session.execute(select(Setting).where(Setting.key == "weekly_zip_enabled"))).scalar_one_or_none()
            ret_setting = (await session.execute(select(Setting).where(Setting.key == "retention_days"))).scalar_one_or_none()

            do_zip = zip_setting.value == "true" if zip_setting else True
            ret_days = int(ret_setting.value) if ret_setting else 30

        if do_zip:
            await perform_weekly_archive(days_back=7)

        await perform_retention_cleanup(retention_days=ret_days)

    except Exception as e:
        logger.error(f"Scheduled weekly maintenance failed: {str(e)}")

async def scheduled_weekly_github_backup():
    logger.info("Scheduler triggered: Starting automated GitHub code backup...")
    try:
        async with AsyncSessionLocal() as session:
            enabled_setting = (await session.execute(select(Setting).where(Setting.key == "github_backup_enabled"))).scalar_one_or_none()
            if enabled_setting and enabled_setting.value == "true":
                await perform_github_backup()
            else:
                logger.info("GitHub backup is disabled in settings. Skipping.")
    except Exception as e:
        logger.error(f"Scheduled GitHub backup failed: {str(e)}")

async def reload_scheduler_jobs():
    """
    Reads latest settings from SQLite DB and configures APScheduler jobs dynamically.
    """
    logger.info("Configuring/reloading scheduler jobs from database...")

    # Clear existing jobs
    for job in scheduler.get_jobs():
        job.remove()

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Setting))
        settings = {s.key: s.value for s in res.scalars().all()}

    # 1. Daily / Interval Footage Sync Job
    sync_enabled = settings.get("schedule_enabled", "true") == "true"
    if sync_enabled:
        mode = settings.get("schedule_mode", "daily")
        if mode == "interval":
            hours = int(settings.get("schedule_interval_hours", "6"))
            scheduler.add_job(
                scheduled_footage_sync,
                trigger=IntervalTrigger(hours=hours),
                id="footage_sync",
                replace_existing=True,
                name=f"Footage Sync every {hours} hours"
            )
            logger.info(f"Registered footage sync job: Interval every {hours} hours")
        else:
            time_parts = settings.get("schedule_time", "02:00").split(":")
            hour = int(time_parts[0]) if len(time_parts) > 0 else 2
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0
            scheduler.add_job(
                scheduled_footage_sync,
                trigger=CronTrigger(hour=hour, minute=minute),
                id="footage_sync",
                replace_existing=True,
                name=f"Daily Footage Sync at {hour:02d}:{minute:02d}"
            )
            logger.info(f"Registered footage sync job: Daily at {hour:02d}:{minute:02d}")

    # 2. Weekly Archive & Retention Job (Every Sunday at 00:00)
    zip_day = int(settings.get("weekly_zip_day", "6")) # 6 = Sunday
    scheduler.add_job(
        scheduled_weekly_maintenance,
        trigger=CronTrigger(day_of_week=zip_day, hour=0, minute=0),
        id="weekly_maintenance",
        replace_existing=True,
        name="Weekly Archival & Retention"
    )
    logger.info(f"Registered weekly maintenance job: Day {zip_day} at 00:00")

    # 3. Weekly GitHub Backup Job (Every Sunday at 01:00)
    gh_day = int(settings.get("github_backup_day", "6"))
    scheduler.add_job(
        scheduled_weekly_github_backup,
        trigger=CronTrigger(day_of_week=gh_day, hour=1, minute=0),
        id="github_backup",
        replace_existing=True,
        name="Weekly GitHub Backup"
    )
    logger.info(f"Registered weekly GitHub backup job: Day {gh_day} at 01:00")

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped.")

import os
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any
from sqlalchemy import select, update

from database import AsyncSessionLocal, Setting

logger = logging.getLogger("percepta.github")

CODE_DIR = os.environ.get("APP_DIR", "/app")

async def get_github_settings() -> Dict[str, str]:
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Setting).where(Setting.key.in_([
                "github_repo_url", "github_token", "github_branch", "github_backup_enabled", "last_github_backup"
            ]))
        )
        settings = {s.key: s.value for s in res.scalars().all()}
        return {
            "repo_url": settings.get("github_repo_url", ""),
            "token": settings.get("github_token", ""),
            "branch": settings.get("github_branch", "main"),
            "enabled": settings.get("github_backup_enabled", "true") == "true",
            "last_backup": settings.get("last_github_backup", "")
        }

def run_git_cmd(cmd_list: list, cwd: str = CODE_DIR) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd_list,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True
    )

async def perform_github_backup() -> Dict[str, Any]:
    """
    Automated Git backup procedure:
    Stages all code changes, commits with timestamp, and pushes to remote GitHub repository.
    Sensitive media footage and SQLite DBs are excluded via .gitignore.
    """
    settings = await get_github_settings()
    repo_url = settings["repo_url"].strip()
    token = settings["token"].strip()
    branch = settings["branch"].strip() or "main"

    if not repo_url:
        return {"success": False, "error": "GitHub repository URL is not configured."}

    # Format authenticated URL
    # e.g., https://github.com/user/repo.git -> https://x-access-token:<token>@github.com/user/repo.git
    auth_url = repo_url
    if token and repo_url.startswith("https://"):
        clean_url = repo_url.replace("https://", "")
        # Remove any existing user info if present
        if "@" in clean_url:
            clean_url = clean_url.split("@", 1)[1]
        auth_url = f"https://x-access-token:{token}@{clean_url}"

    logger.info(f"Initiating GitHub backup to branch '{branch}'...")

    try:
        # 1. Initialize git if not already a git repository
        git_dir = os.path.join(CODE_DIR, ".git")
        if not os.path.exists(git_dir):
            run_git_cmd(["git", "init", "-b", branch])
            logger.info("Initialized local git repository.")

        # 2. Configure bot identity
        run_git_cmd(["git", "config", "user.name", "Percepta Backup Bot"])
        run_git_cmd(["git", "config", "user.email", "percepta-bot@local"])

        # 3. Add or update remote
        remotes_proc = run_git_cmd(["git", "remote"])
        remotes = remotes_proc.stdout.split()
        if "origin" in remotes:
            run_git_cmd(["git", "remote", "set-url", "origin", auth_url])
        else:
            run_git_cmd(["git", "remote", "add", "origin", auth_url])

        # 4. Stage files
        run_git_cmd(["git", "add", "-A"])

        # 5. Check if there are changes to commit
        status_proc = run_git_cmd(["git", "status", "--porcelain"])
        has_changes = bool(status_proc.stdout.strip())

        timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        commit_msg = f"Automated Percepta Backup: {timestamp_str}"

        if has_changes:
            run_git_cmd(["git", "commit", "-m", commit_msg])
            logger.info("Committed changes.")
        else:
            logger.info("No file changes detected since last backup; pushing existing commits if unpushed.")

        # 6. Push to remote
        push_proc = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=CODE_DIR,
            capture_output=True,
            text=True
        )

        if push_proc.returncode != 0:
            err = push_proc.stderr.replace(token, "******") if token else push_proc.stderr
            logger.error(f"Git push failed: {err}")
            return {"success": False, "error": f"Git push failed: {err}"}

        # 7. Record last backup timestamp
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(Setting).where(Setting.key == "last_github_backup").values(value=timestamp_str)
            )
            await session.commit()

        logger.info(f"GitHub backup completed successfully at {timestamp_str}!")
        return {
            "success": True,
            "message": f"Successfully backed up to GitHub ({branch})",
            "timestamp": timestamp_str
        }

    except subprocess.CalledProcessError as e:
        safe_err = e.stderr.replace(token, "******") if token else e.stderr
        logger.error(f"Git process error: {safe_err}")
        return {"success": False, "error": safe_err}
    except Exception as ex:
        logger.error(f"Unexpected error during GitHub backup: {str(ex)}")
        return {"success": False, "error": str(ex)}

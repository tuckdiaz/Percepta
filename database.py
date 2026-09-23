import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from passlib.context import CryptContext

DB_DIR = os.environ.get("DATA_DIR", "/app/data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "percepta.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="admin", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    ip = Column(String(50), nullable=False)
    cloud_password = Column(String(255), nullable=False)
    user = Column(String(100), default="admin", nullable=False)
    password = Column(String(255), default="", nullable=False)
    window_size = Column(Integer, default=50, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    last_sync = Column(DateTime, nullable=True)
    last_status = Column(String(100), default="idle", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)

class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True, index=True)
    camera_name = Column(String(100), nullable=False, index=True)
    date_str = Column(String(20), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    status = Column(String(50), nullable=False)
    message = Column(Text, default="")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default user and settings
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        # Check default admin
        res = await session.execute(select(User).where(User.username == "admin"))
        admin = res.scalar_one_or_none()
        if not admin:
            admin = User(
                username="admin",
                password_hash=hash_password("admin@123"),
                role="admin"
            )
            session.add(admin)

        # Default settings
        default_settings = {
            "storage_path": os.environ.get("STORAGE_DIR", "/storage"),
            "schedule_time": "02:00",
            "schedule_enabled": "true",
            "schedule_mode": "daily",  # daily or interval
            "schedule_interval_hours": "6",
            "ram_limit_pct": "90",
            "retention_days": "30",
            "weekly_zip_enabled": "true",
            "weekly_zip_day": "6",  # 0=Mon, 6=Sun
            "github_repo_url": "",
            "github_token": "",
            "github_branch": "main",
            "github_backup_enabled": "true",
            "github_backup_day": "6",  # Sunday
            "last_github_backup": "",
            "last_weekly_archive": ""
        }

        for k, v in default_settings.items():
            res = await session.execute(select(Setting).where(Setting.key == k))
            if not res.scalar_one_or_none():
                session.add(Setting(key=k, value=v))

        await session.commit()

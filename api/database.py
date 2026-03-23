"""
数据库连接管理和初始化。

使用 SQLAlchemy 异步引擎管理 SQLite 连接，支持 FastAPI 生命周期。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from api import config


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。"""

    pass


engine = create_async_engine(
    config.DATABASE_URL,
    echo=False,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """
    初始化数据库，创建所有表。

    在 FastAPI 应用启动时调用。
    """
    db_path = Path(config.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    关闭数据库连接。

    在 FastAPI 应用关闭时调用。
    """
    await engine.dispose()


@asynccontextmanager
async def get_db_session() -> AsyncSession:
    """
    获取数据库会话的上下文管理器。

    用于路由中直接使用：
        async with get_db_session() as session:
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

"""
数据库连接管理和初始化。

使用 SQLAlchemy 异步引擎管理 SQLite 连接，支持 FastAPI 生命周期。
"""

from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncGenerator, Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection
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


def _table_exists(conn: Connection, table_name: str) -> bool:
    row = conn.execute(
        text(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = :table_name
            """
        ),
        {"table_name": table_name},
    ).fetchone()
    return row is not None


def _column_exists(conn: Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def _ensure_schema_migrations_table(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at INTEGER NOT NULL
            )
            """
        )
    )


def _is_migration_applied(conn: Connection, version: int) -> bool:
    row = conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE version = :version"),
        {"version": version},
    ).fetchone()
    return row is not None


def _record_migration(conn: Connection, version: int, name: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO schema_migrations (version, name, applied_at)
            VALUES (:version, :name, CAST(strftime('%s', 'now') AS INTEGER))
            """
        ),
        {"version": version, "name": name},
    )


def _apply_migration_1(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pdf_name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                authors TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS paper_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                is_current BOOLEAN NOT NULL DEFAULT 1,
                source_hash TEXT NOT NULL,
                ingestion_schema_version INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE (paper_id, version_number),
                FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                id TEXT PRIMARY KEY,
                paper_id INTEGER NOT NULL,
                paper_version_id INTEGER,
                status TEXT NOT NULL,
                stage TEXT NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                retry_count INTEGER NOT NULL DEFAULT 0,
                source_file_path TEXT NOT NULL,
                result_summary TEXT,
                error_message TEXT,
                leased_at INTEGER,
                leased_by TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE,
                FOREIGN KEY(paper_version_id) REFERENCES paper_versions(id) ON DELETE SET NULL
            )
            """
        )
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_papers_pdf_name ON papers (pdf_name)"))
    conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_paper_versions_paper_id ON paper_versions (paper_id)")
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_paper_id ON ingestion_jobs (paper_id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_paper_version_id ON ingestion_jobs (paper_version_id)"
        )
    )


def _apply_migration_2(conn: Connection) -> None:
    # Defensive migration for older partial schemas (safe no-op when columns exist)
    table_name = "ingestion_jobs"
    if not _table_exists(conn, table_name):
        return

    alter_statements: dict[str, str] = {
        "status": "ALTER TABLE ingestion_jobs ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
        "stage": "ALTER TABLE ingestion_jobs ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'",
        "progress": "ALTER TABLE ingestion_jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0",
        "retry_count": "ALTER TABLE ingestion_jobs ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0",
        "source_file_path": "ALTER TABLE ingestion_jobs ADD COLUMN source_file_path TEXT NOT NULL DEFAULT ''",
        "result_summary": "ALTER TABLE ingestion_jobs ADD COLUMN result_summary TEXT",
        "error_message": "ALTER TABLE ingestion_jobs ADD COLUMN error_message TEXT",
        "updated_at": "ALTER TABLE ingestion_jobs ADD COLUMN updated_at INTEGER NOT NULL DEFAULT 0",
    }

    for column_name, statement in alter_statements.items():
        if not _column_exists(conn, table_name, column_name):
            conn.execute(text(statement))


def _apply_migration_3(conn: Connection) -> None:
    table_name = "ingestion_jobs"
    if not _table_exists(conn, table_name):
        return

    alter_statements: dict[str, str] = {
        "leased_at": "ALTER TABLE ingestion_jobs ADD COLUMN leased_at INTEGER",
        "leased_by": "ALTER TABLE ingestion_jobs ADD COLUMN leased_by TEXT",
    }

    for column_name, statement in alter_statements.items():
        if not _column_exists(conn, table_name, column_name):
            conn.execute(text(statement))


def _run_migrations(conn: Connection) -> None:
    _ensure_schema_migrations_table(conn)
    migrations: list[tuple[int, str, Callable[[Connection], None]]] = [
        (1, "create_papers_versions_jobs", _apply_migration_1),
        (2, "ensure_ingestion_job_columns", _apply_migration_2),
        (3, "add_ingestion_job_lease_columns", _apply_migration_3),
    ]

    for version, name, migration in migrations:
        if _is_migration_applied(conn, version):
            continue
        migration(conn)
        _record_migration(conn, version, name)


def _bootstrap_schema(conn: Connection) -> None:
    from api import models  # noqa: F401

    Base.metadata.create_all(conn)
    _run_migrations(conn)


async def init_db() -> None:
    """
    初始化数据库，创建所有表。

    在 FastAPI 应用启动时调用。
    """
    db_path = Path(config.DATABASE_URL.replace("sqlite+aiosqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)


async def close_db() -> None:
    """
    关闭数据库连接。

    在 FastAPI 应用关闭时调用。
    """
    await engine.dispose()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
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

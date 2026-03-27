import sqlite3
import tempfile
from pathlib import Path

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")

from sqlalchemy import text  # type: ignore[reportMissingImports]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # type: ignore[reportMissingImports]

from api.database import _bootstrap_schema
from api.schemas import MessageCreate
from api.services import conversation_service
from api.services.ingestion_job_service import create_ingestion_job, update_ingestion_job
from api.services.paper_registry_service import create_or_get_paper, create_paper_version


@pytest.mark.asyncio
async def test_schema_bootstrap_idempotent_creates_required_tables() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)
        await conn.run_sync(_bootstrap_schema)

    await engine.dispose()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    Path(db_path).unlink(missing_ok=True)

    table_names = {row[0] for row in rows}
    assert "conversations" in table_names
    assert "messages" in table_names
    assert "papers" in table_names
    assert "paper_versions" in table_names
    assert "ingestion_jobs" in table_names


@pytest.mark.asyncio
async def test_version_current_toggling_and_job_state_transitions(
    db_session: AsyncSession,
) -> None:
    paper = await create_or_get_paper(
        db_session,
        pdf_name="test-paper",
        title="Test Paper",
        authors="Alice|Bob",
    )

    version_1 = await create_paper_version(
        db_session,
        paper_id=paper.id,
        source_hash="hash-v1",
        ingestion_schema_version=3,
    )
    assert version_1.version_number == 1
    assert version_1.is_current is True

    version_2 = await create_paper_version(
        db_session,
        paper_id=paper.id,
        source_hash="hash-v2",
        ingestion_schema_version=3,
    )
    assert version_2.version_number == 2
    assert version_2.is_current is True
    await db_session.refresh(version_1)
    assert version_1.is_current is False

    job = await create_ingestion_job(
        db_session,
        job_id="job-1",
        paper_id=paper.id,
        paper_version_id=version_2.id,
        source_file_path="/tmp/test-paper.pdf",
    )
    assert job.status == "pending"
    assert job.stage == "queued"
    assert job.progress == 0

    processing_job = await update_ingestion_job(
        db_session,
        job_id="job-1",
        status="processing",
        stage="chunking",
        progress=35,
    )
    assert processing_job is not None
    assert processing_job.status == "processing"
    assert processing_job.stage == "chunking"
    assert processing_job.progress == 35

    completed_job = await update_ingestion_job(
        db_session,
        job_id="job-1",
        status="completed",
        stage="finalizing",
        progress=100,
        result_summary='{"chunks": 12}',
        error_message=None,
    )
    assert completed_job is not None
    assert completed_job.status == "completed"
    assert completed_job.progress == 100
    assert completed_job.result_summary == '{"chunks": 12}'


@pytest.mark.asyncio
async def test_job_and_version_rows_persist_after_restart() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url, echo=False)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)

    async with session_maker() as session:
        paper = await create_or_get_paper(
            session,
            pdf_name="persisted-paper",
            title="Persisted Paper",
            authors="Author A",
        )
        version = await create_paper_version(
            session,
            paper_id=paper.id,
            source_hash="persisted-hash",
            ingestion_schema_version=3,
        )
        await create_ingestion_job(
            session,
            job_id="persisted-job",
            paper_id=paper.id,
            paper_version_id=version.id,
            source_file_path="/tmp/persisted-paper.pdf",
            status="processing",
            stage="storing",
            progress=70,
        )
        await session.commit()

    async with session_maker() as reopened_session:
        rows = await reopened_session.execute(
            text(
                """
                SELECT p.pdf_name, pv.version_number, pv.is_current, ij.status, ij.stage, ij.progress
                FROM papers p
                JOIN paper_versions pv ON pv.paper_id = p.id
                JOIN ingestion_jobs ij ON ij.paper_id = p.id
                WHERE p.pdf_name = :pdf_name
                """
            ),
            {"pdf_name": "persisted-paper"},
        )
        data = rows.one()
        assert data.pdf_name == "persisted-paper"
        assert data.version_number == 1
        assert data.is_current == 1
        assert data.status == "processing"
        assert data.stage == "storing"
        assert data.progress == 70

    await engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_conversation_crud_path_still_works(db_session: AsyncSession) -> None:
    conversation_id = "conv-unchanged"
    await conversation_service.create_conversation(
        db_session,
        conversation_id=conversation_id,
        title="Compat Conversation",
    )

    message = MessageCreate(
        id="msg-1",
        role="user",
        content="hello",
        created_at=123,
    )
    created = await conversation_service.add_message(db_session, conversation_id, message)
    assert created is not None

    conversation = await conversation_service.get_conversation(db_session, conversation_id)
    assert conversation is not None
    assert len(conversation.messages) == 1
    assert conversation.messages[0].content == "hello"

import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import Paper, PaperVersion


def _now_ms() -> int:
    return int(time.time() * 1000)


async def get_paper_by_pdf_name(
    session: AsyncSession, pdf_name: str
) -> Optional[Paper]:
    result = await session.execute(select(Paper).where(Paper.pdf_name == pdf_name))
    return result.scalar_one_or_none()


async def create_or_get_paper(
    session: AsyncSession,
    pdf_name: str,
    title: str,
    authors: str,
) -> Paper:
    existing = await get_paper_by_pdf_name(session, pdf_name)
    if existing is not None:
        existing.title = title
        existing.authors = authors
        existing.updated_at = _now_ms()
        await session.flush()
        return existing

    now = _now_ms()
    paper = Paper(
        pdf_name=pdf_name,
        title=title,
        authors=authors,
        created_at=now,
        updated_at=now,
    )
    session.add(paper)
    await session.flush()
    return paper


async def get_current_version(
    session: AsyncSession,
    paper_id: int,
) -> Optional[PaperVersion]:
    result = await session.execute(
        select(PaperVersion)
        .where(PaperVersion.paper_id == paper_id, PaperVersion.is_current.is_(True))
        .order_by(PaperVersion.version_number.desc())
    )
    return result.scalar_one_or_none()


async def list_versions(session: AsyncSession, paper_id: int) -> list[PaperVersion]:
    result = await session.execute(
        select(PaperVersion)
        .where(PaperVersion.paper_id == paper_id)
        .order_by(PaperVersion.version_number.asc())
    )
    return list(result.scalars().all())


async def create_paper_version(
    session: AsyncSession,
    paper_id: int,
    source_hash: str,
    ingestion_schema_version: int,
    make_current: bool = True,
) -> PaperVersion:
    versions = await list_versions(session, paper_id)
    version_number = (versions[-1].version_number + 1) if versions else 1

    if make_current:
        for version in versions:
            if version.is_current:
                version.is_current = False

    version = PaperVersion(
        paper_id=paper_id,
        version_number=version_number,
        is_current=make_current,
        source_hash=source_hash,
        ingestion_schema_version=ingestion_schema_version,
        created_at=_now_ms(),
    )
    session.add(version)
    await session.flush()
    return version


async def set_current_version(
    session: AsyncSession,
    paper_id: int,
    version_id: int,
) -> Optional[PaperVersion]:
    versions = await list_versions(session, paper_id)
    if not versions:
        return None

    selected: Optional[PaperVersion] = None
    for version in versions:
        version.is_current = version.id == version_id
        if version.is_current:
            selected = version

    await session.flush()
    return selected

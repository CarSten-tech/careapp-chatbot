"""
Test-Infrastruktur. Tests laufen gegen Supabase (echte Postgres-Instanz).
Schema ist via Migration vorbereitet. Jeder Test bekommt eine frische Engine
(eigener asyncpg-Pool, kein Event-Loop-Konflikt).
"""

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()


def pytest_collection_modifyitems(config, items):
    """Überspringt llm-markierte Tests wenn kein LLM-Key gesetzt ist."""
    has_llm = bool(
        os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("NVIDIA_API_KEY")
    )
    if has_llm:
        return
    skip = pytest.mark.skip(reason="Kein LLM-Key gesetzt — Live-LLM-Test übersprungen")
    for item in items:
        if item.get_closest_marker("llm"):
            item.add_marker(skip)

# Reihenfolge: explizite Test-DB > DATABASE_URL (CI setzt nur diese) > lokaler Default.
TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql+asyncpg://careapp:careapp_dev@localhost:5433/careapp_test"
)


@pytest.fixture
async def engine():
    """Frische Engine + asyncpg-Pool pro Test — verhindert Loop-Konflikte."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield _engine
    await _engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        yield s
        await s.rollback()

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

# Lokale Hosts, gegen die destruktive Tests (TRUNCATE in db_clean) laufen dürfen.
_LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "", None})


def pytest_sessionstart(session) -> None:
    """Sicherheits-Guard: Die db_clean-Fixture TRUNCATEt alle Tabellen. Läuft sie
    versehentlich gegen eine entfernte (Produktions-)DB, gehen echte Daten verloren.
    Darum: Test-Session hart abbrechen, wenn TEST_DATABASE_URL nicht auf einen
    lokalen Host zeigt — außer explizitem Opt-in CAREAPP_ALLOW_PROD_TESTS=1.
    """
    if os.environ.get("CAREAPP_ALLOW_PROD_TESTS") == "1":
        return
    from sqlalchemy.engine import make_url

    try:
        host = make_url(TEST_DATABASE_URL).host
    except Exception:  # nicht parsebar → konservativ blockieren
        host = "<unparsable>"
    if host not in _LOCAL_DB_HOSTS:
        pytest.exit(
            f"\n\nABBRUCH: TEST_DATABASE_URL zeigt auf einen nicht-lokalen Host "
            f"('{host}'). Tests führen TRUNCATE aus und würden dort echte Daten "
            f"löschen.\nNutze eine lokale Test-DB (z. B. localhost) oder setze "
            f"bewusst CAREAPP_ALLOW_PROD_TESTS=1, wenn du das wirklich willst.\n",
            returncode=2,
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

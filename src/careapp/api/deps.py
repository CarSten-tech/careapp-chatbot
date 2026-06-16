"""
FastAPI Dependencies (Layer 6).

Alle Abhängigkeiten sind über `app.dependency_overrides` ersetzbar — das ist
das Testbarkeits-Muster: kein Monkeypatching, keine globalen Singletons.

Produktiv:
  - DB:    AsyncSession gegen Supabase (DATABASE_URL)
  - LLM:   AnthropicLLMClient (ANTHROPIC_API_KEY) oder FakeLLMClient (DEV_LLM=fake)
  - Store: SupabaseCheckpointStore (nutzt dieselbe DB-Session)
  - Cfg:   GraphConfig aus Env-Vars (Defaults = Pilot-Versions)

Tests:
  app.dependency_overrides[get_db_session] = lambda: fake_session_context_manager
  app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient(...)
  app.dependency_overrides[get_checkpoint_store_for_session] = lambda: InMemoryCheckpointStore()
"""

import os
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from careapp.llm.port import FakeLLMClient, LLMClient
from careapp.orchestration.checkpoint import (
    CheckpointStore,
    InMemoryCheckpointStore,
    SupabaseCheckpointStore,
)
from careapp.orchestration.state import GraphConfig

# ------------------------------------------------------------------ #
# DB                                                                  #
# ------------------------------------------------------------------ #

_db_engine = None
_db_session_maker = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _db_engine, _db_session_maker
    if _db_session_maker is None:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://careapp:careapp_dev@localhost:5432/careapp",
        )
        _db_engine = create_async_engine(url, echo=False, pool_pre_ping=True)
        _db_session_maker = async_sessionmaker(_db_engine, expire_on_commit=False)
    return _db_session_maker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    session_maker = _get_session_maker()
    async with session_maker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]

# ------------------------------------------------------------------ #
# LLM                                                                 #
# ------------------------------------------------------------------ #


def get_llm_client() -> LLMClient:
    """
    Priorität:
    1. DEV_LLM=fake → FakeLLMClient (kein LLM-Aufruf)
    2. NVIDIA_API_KEY gesetzt → OpenAICompatLLMClient (NVIDIA NIM / Kimi K2.6)
    3. ANTHROPIC_API_KEY gesetzt → AnthropicLLMClient
    Tests überschreiben via dependency_overrides.
    """
    if os.environ.get("DEV_LLM") == "fake":
        return FakeLLMClient()

    if os.environ.get("NVIDIA_API_KEY"):
        try:
            from careapp.llm.openai_compat_adapter import OpenAICompatLLMClient
        except ImportError:
            raise RuntimeError(
                "OpenAICompatLLMClient nicht verfügbar — uv sync --extra llm ausführen."
            )
        return OpenAICompatLLMClient(
            api_key=os.environ["NVIDIA_API_KEY"],
            base_url=os.environ.get(
                "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
            ),
            default_model_id=os.environ.get(
                "NVIDIA_MODEL_ID", "moonshotai/kimi-k2.6"
            ),
        )

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from careapp.llm.anthropic_adapter import AnthropicLLMClient  # type: ignore[import]

            return AnthropicLLMClient()
        except ImportError:
            raise RuntimeError(
                "AnthropicLLMClient nicht verfügbar — uv sync --extra llm ausführen."
            )

    raise RuntimeError(
        "Kein LLM-Anbieter konfiguriert. "
        "Setze NVIDIA_API_KEY oder ANTHROPIC_API_KEY, oder DEV_LLM=fake für Entwicklung."
    )


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


def get_embedder() -> object | None:
    """Embedding-Client für den semantischen Recall. None → Semantik deaktiviert
    (das Retrieval fällt graceful auf das bisherige Verhalten zurück).
    NVIDIA NIM, gleicher Key wie das LLM."""
    if not os.environ.get("NVIDIA_API_KEY"):
        return None
    try:
        from careapp.llm.embeddings import NIMEmbeddingClient
    except ImportError:
        return None
    return NIMEmbeddingClient(
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url=os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        model=os.environ.get("NVIDIA_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5"),
    )


EmbedderDep = Annotated[object | None, Depends(get_embedder)]

# ------------------------------------------------------------------ #
# Checkpoint Store                                                    #
# ------------------------------------------------------------------ #


def get_checkpoint_store(session: DbSession) -> CheckpointStore:
    """
    Produktiv: SupabaseCheckpointStore (nutzt die laufende DB-Session).
    Tests überschreiben via dependency_overrides.
    """
    if os.environ.get("CAREAPP_DEV_AUTH") == "true" and os.environ.get("DEV_INMEMORY_STORE"):
        return InMemoryCheckpointStore()
    return SupabaseCheckpointStore(session)


CheckpointStoreDep = Annotated[CheckpointStore, Depends(get_checkpoint_store)]

# ------------------------------------------------------------------ #
# Graph Config                                                        #
# ------------------------------------------------------------------ #


def get_graph_config() -> GraphConfig:
    return GraphConfig(
        graph_version=os.environ.get("CAREAPP_GRAPH_VERSION", "graph-v1"),
        prompt_set_version=os.environ.get("CAREAPP_PROMPT_VERSION", "prompts-v1"),
        model_version=os.environ.get("CAREAPP_MODEL_VERSION", "models-v1"),
    )


GraphConfigDep = Annotated[GraphConfig, Depends(get_graph_config)]

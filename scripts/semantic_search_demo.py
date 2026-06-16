"""
Demo: semantische Suche über die Claim-Embeddings (Hybrid-Retrieval, Recall-Stufe).

Bettet die übergebene Frage als `query` ein und rankt die publizierten Claims
nach Cosine-Ähnlichkeit. Zeigt NUR den Recall — die Eligibility-Filter (Region/
Mandant/Gültigkeit) sind hier bewusst nicht angewandt; es geht um „findet die
Suche die richtigen Claims, auch bei freier Formulierung?".

Ausführen:
    uv run --extra llm python scripts/semantic_search_demo.py "deine frage hier"
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from careapp.llm.embeddings import NIMEmbeddingClient, embedding_to_pgvector


async def main(query: str, k: int = 4) -> None:
    load_dotenv()
    client = NIMEmbeddingClient(api_key=os.environ["NVIDIA_API_KEY"])
    qvec = embedding_to_pgvector(client.embed_query(query))

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT statement_text, 1 - (embedding <=> (:q)::vector) AS sim "
                        "FROM claim_version "
                        "WHERE status = 'published' AND embedding IS NOT NULL "
                        "ORDER BY embedding <=> (:q)::vector LIMIT :k"
                    ),
                    {"q": qvec, "k": k},
                )
            ).all()
    finally:
        await engine.dispose()

    print(f'\nFrage: "{query}"\nTop {k} Claims nach Ähnlichkeit:\n')
    for stmt, sim in rows:
        print(f"  {sim:.3f}  {stmt[:95]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit('Nutzung: python scripts/semantic_search_demo.py "frage"')
    asyncio.run(main(sys.argv[1]))

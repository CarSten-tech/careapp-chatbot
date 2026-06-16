"""
Backfill: Embeddings für publizierte ClaimVersions berechnen und speichern.

Lädt alle published ClaimVersions, bettet `statement_text` als passage über NIM
ein und schreibt den Vektor in die Spalte `claim_version.embedding` (Migration 0005).

Idempotent: überspringt CVs, die bereits ein Embedding haben (außer --force).

Ausführen:
    uv run python scripts/backfill_embeddings.py
    uv run python scripts/backfill_embeddings.py --dry-run   # nur zählen, nichts schreiben
    uv run python scripts/backfill_embeddings.py --force     # auch vorhandene neu berechnen
"""

import argparse
import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from careapp.llm.embeddings import NIMEmbeddingClient, embedding_to_pgvector


async def main(dry_run: bool, force: bool) -> None:
    load_dotenv()
    db_url = os.environ["DATABASE_URL"]
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise SystemExit("NVIDIA_API_KEY fehlt — Embedding nicht möglich.")

    engine = create_async_engine(db_url)
    where_embedding = "" if force else " AND embedding IS NULL"
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, statement_text FROM claim_version "
                        f"WHERE status = 'published'{where_embedding} "
                        "ORDER BY id"
                    )
                )
            ).all()

        if not rows:
            print("Nichts zu tun: alle publizierten Claims haben bereits ein Embedding.")
            return

        print(f"{len(rows)} Claim(s) zu embedden (force={force}, dry_run={dry_run}).")
        for cv_id, stmt in rows:
            print(f"  - {str(cv_id)[:8]}…  {stmt[:70]}")

        if dry_run:
            print("Dry-run: nichts geschrieben.")
            return

        client = NIMEmbeddingClient(api_key=api_key)
        vectors = client.embed([r[1] for r in rows], input_type="passage")

        async with engine.begin() as conn:
            for (cv_id, _stmt), vec in zip(rows, vectors):
                await conn.execute(
                    text("UPDATE claim_version SET embedding = (:emb)::vector WHERE id = :id"),
                    {"emb": embedding_to_pgvector(vec), "id": cv_id},
                )
        print(f"✓ {len(rows)} Embedding(s) gespeichert.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(dry_run=args.dry_run, force=args.force))

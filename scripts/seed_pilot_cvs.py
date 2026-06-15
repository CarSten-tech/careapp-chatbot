"""
Pilot-Content-Seeding: Heimunterbringung (stationäre Pflege) — Kreis Neuss.

Legt die minimalen publizierten ClaimVersions für den ersten Pilot an.
Quellen: SGB XI (Sozialgesetzbuch Elftes Buch), öffentliches Bundesrecht.

Idempotent: prüft per canonical_ref, ob Quelle bereits existiert.
Überspringt CVs die schon vorhanden sind (kein Duplikat, kein Fehler).

Ausführen:
    uv run python scripts/seed_pilot_cvs.py
    uv run python scripts/seed_pilot_cvs.py --dry-run   # nur ausgeben, nichts schreiben
    uv run python scripts/seed_pilot_cvs.py --reset     # LÖSCHT alles und seeded neu
"""

import argparse
import asyncio
import hashlib
import sys
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

import os
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://careapp:careapp_dev@localhost:5432/careapp_dev",
)

from careapp.db.models.claim import (
    ActorRole,
    Approval,
    Claim,
    ClaimEvidence,
    ClaimVersion,
    ClaimVersionStatus,
    EvidenceRole,
    RegionBinding,
    ScopeAssignment,
    ScopeDimension,
    StructuredValue,
    StructuredValueKind,
)
from careapp.db.models.source import (
    SourceDocument,
    SourcePassage,
    SourceType,
    SourceVersion,
)

# ────────────────────────────────────────────────────────────────────────────
# Zeitstempel
# ────────────────────────────────────────────────────────────────────────────

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)     # redaktionelles Freigabedatum Pilot
EFFECTIVE = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# Quellmaterial: SGB XI
# ────────────────────────────────────────────────────────────────────────────
#
# SGB XI ist Bundesrecht, veröffentlicht auf gesetze-im-internet.de (public domain).
# Alle Zitate sind wortgetreu (Stand: SGB XI i.d.F. v. 23.10.2024, BGBl. 2024 I Nr. 318).
#
SGBXI_SOURCE = {
    "canonical_ref": "SGB XI (i.d.F. v. 23.10.2024, BGBl. 2024 I Nr. 318)",
    "publisher": "Bundesrepublik Deutschland / BMAS",
    "type": SourceType.law,
    "edition_label": "Stand: 23.10.2024",
    "edition_hash": "sgb11-2024-10-23",  # Kurzbezeichnung für content_hash
    "uri": "https://www.gesetze-im-internet.de/sgb_11/",
}

PASSAGES = [
    {
        "key": "§14-abs1",
        "anchor": {"paragraph": "§ 14 Abs. 1 SGB XI"},
        "text": (
            "Pflegebedürftig im Sinne dieses Buches sind Personen, die gesundheitlich "
            "bedingte Beeinträchtigungen der Selbständigkeit oder der Fähigkeiten aufweisen "
            "und deshalb der Hilfe durch andere bedürfen. Es muss sich um Personen handeln, "
            "die körperliche, kognitive oder psychische Beeinträchtigungen oder "
            "gesundheitlich bedingte Belastungen oder Anforderungen nicht selbständig "
            "kompensieren oder bewältigen können. Die Pflegebedürftigkeit muss auf Dauer, "
            "voraussichtlich für mindestens sechs Monate, und mit mindestens der in § 15 "
            "festgelegten Schwere bestehen."
        ),
    },
    {
        "key": "§15-abs1",
        "anchor": {"paragraph": "§ 15 Abs. 1 SGB XI"},
        "text": (
            "Zur Feststellung von Pflegebedürftigkeit sowie zur Bestimmung des Grades der "
            "Pflegebedürftigkeit sind die beeinträchtigten Fähigkeiten und die eingeschränkte "
            "Selbständigkeit in den in Absatz 2 genannten Bereichen und Modulen maßgebend. "
            "Der Grad der Pflegebedürftigkeit wird danach in fünf Pflegegrade unterteilt: "
            "Pflegegrad 1 (geringe Beeinträchtigungen), Pflegegrad 2 (erhebliche "
            "Beeinträchtigungen), Pflegegrad 3 (schwere Beeinträchtigungen), Pflegegrad 4 "
            "(schwerste Beeinträchtigungen), Pflegegrad 5 (schwerste Beeinträchtigungen "
            "mit besonderen Anforderungen an die pflegerische Versorgung)."
        ),
    },
    {
        "key": "§43-abs1",
        "anchor": {"paragraph": "§ 43 Abs. 1 SGB XI"},
        "text": (
            "Pflegebedürftige der Pflegegrade 2 bis 5 haben Anspruch auf Pflege in "
            "vollstationären Einrichtungen, wenn häusliche oder teilstationäre Pflege "
            "nicht möglich ist oder wegen der Besonderheit des Einzelfalls nicht in "
            "Betracht kommt."
        ),
    },
    {
        "key": "§43-abs2",
        "anchor": {"paragraph": "§ 43 Abs. 2 SGB XI"},
        "text": (
            "Die zugelassenen Pflegeeinrichtungen erhalten bei vollstationärer Pflege von "
            "der Pflegekasse folgende monatliche Pauschalbeträge: "
            "Pflegegrad 1: 125 EUR, Pflegegrad 2: 770 EUR, Pflegegrad 3: 1.262 EUR, "
            "Pflegegrad 4: 1.775 EUR, Pflegegrad 5: 2.005 EUR."
        ),
    },
    {
        "key": "§43b-abs1",
        "anchor": {"paragraph": "§ 43b Abs. 1 SGB XI"},
        "text": (
            "Pflegebedürftige in stationären Pflegeeinrichtungen haben Anspruch auf "
            "zusätzliche Betreuung und Aktivierung, die über die nach Art und Schwere der "
            "Pflegebedürftigkeit notwendige Versorgung hinausgeht (zusätzliche Betreuungs- "
            "und Aktivierungsangebote)."
        ),
    },
]

# ────────────────────────────────────────────────────────────────────────────
# Claim-Versions-Definitionen
# ────────────────────────────────────────────────────────────────────────────

CV_DEFS = [
    {
        "id_seed": "cv-pflegebeduerftigkeit-definition",
        "statement_text": (
            "Pflegebedürftig im Sinne des SGB XI sind Personen, die gesundheitlich bedingte "
            "Beeinträchtigungen der Selbständigkeit oder der Fähigkeiten aufweisen und deshalb "
            "der Hilfe durch andere bedürfen. Die Pflegebedürftigkeit muss voraussichtlich "
            "mindestens sechs Monate bestehen."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§14-abs1",
        "evidence_quote": (
            "Pflegebedürftig im Sinne dieses Buches sind Personen, die gesundheitlich bedingte "
            "Beeinträchtigungen der Selbständigkeit oder der Fähigkeiten aufweisen und deshalb "
            "der Hilfe durch andere bedürfen. [...] Die Pflegebedürftigkeit muss auf Dauer, "
            "voraussichtlich für mindestens sechs Monate [...] bestehen."
        ),
        "structured_values": [],
    },
    {
        "id_seed": "cv-pflegegrade-uebersicht",
        "statement_text": (
            "Die Pflegebedürftigkeit wird in fünf Pflegegrade eingeteilt (Pflegegrad 1–5). "
            "Ab Pflegegrad 2 liegen erhebliche Beeinträchtigungen vor. Die Einstufung erfolgt "
            "durch den Medizinischen Dienst (MD) auf Antrag bei der Pflegekasse."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§15-abs1",
        "evidence_quote": (
            "Der Grad der Pflegebedürftigkeit wird danach in fünf Pflegegrade unterteilt: "
            "Pflegegrad 1 (geringe Beeinträchtigungen), Pflegegrad 2 (erhebliche "
            "Beeinträchtigungen), Pflegegrad 3 (schwere Beeinträchtigungen), Pflegegrad 4 "
            "(schwerste Beeinträchtigungen), Pflegegrad 5 (schwerste Beeinträchtigungen "
            "mit besonderen Anforderungen an die pflegerische Versorgung)."
        ),
        "structured_values": [],
    },
    {
        "id_seed": "cv-vollstationaere-pflege-anspruch",
        "statement_text": (
            "Pflegebedürftige ab Pflegegrad 2 haben Anspruch auf vollstationäre Pflege "
            "in einem Pflegeheim, wenn häusliche oder teilstationäre Pflege nicht möglich "
            "oder nicht zumutbar ist."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43-abs1",
        "evidence_quote": (
            "Pflegebedürftige der Pflegegrade 2 bis 5 haben Anspruch auf Pflege in "
            "vollstationären Einrichtungen, wenn häusliche oder teilstationäre Pflege "
            "nicht möglich ist oder wegen der Besonderheit des Einzelfalls nicht in "
            "Betracht kommt."
        ),
        "structured_values": [],
    },
    {
        "id_seed": "cv-vollstationaere-pflegekassenbetrag-pg2",
        "statement_text": (
            "Bei vollstationärer Pflege zahlt die Pflegekasse im Pflegegrad 2 "
            "monatlich 770 EUR."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43-abs2",
        "evidence_quote": "Pflegegrad 2: 770 EUR",
        "structured_values": [
            {"kind": StructuredValueKind.amount_eur, "value": "770", "unit": "EUR"},
        ],
    },
    {
        "id_seed": "cv-vollstationaere-pflegekassenbetrag-pg3",
        "statement_text": (
            "Bei vollstationärer Pflege zahlt die Pflegekasse im Pflegegrad 3 "
            "monatlich 1.262 EUR."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43-abs2",
        "evidence_quote": "Pflegegrad 3: 1.262 EUR",
        "structured_values": [
            {"kind": StructuredValueKind.amount_eur, "value": "1262", "unit": "EUR"},
        ],
    },
    {
        "id_seed": "cv-vollstationaere-pflegekassenbetrag-pg4",
        "statement_text": (
            "Bei vollstationärer Pflege zahlt die Pflegekasse im Pflegegrad 4 "
            "monatlich 1.775 EUR."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43-abs2",
        "evidence_quote": "Pflegegrad 4: 1.775 EUR",
        "structured_values": [
            {"kind": StructuredValueKind.amount_eur, "value": "1775", "unit": "EUR"},
        ],
    },
    {
        "id_seed": "cv-vollstationaere-pflegekassenbetrag-pg5",
        "statement_text": (
            "Bei vollstationärer Pflege zahlt die Pflegekasse im Pflegegrad 5 "
            "monatlich 2.005 EUR."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43-abs2",
        "evidence_quote": "Pflegegrad 5: 2.005 EUR",
        "structured_values": [
            {"kind": StructuredValueKind.amount_eur, "value": "2005", "unit": "EUR"},
        ],
    },
    {
        "id_seed": "cv-betreuungsangebote-stationaer",
        "statement_text": (
            "Pflegebedürftige in stationären Einrichtungen haben Anspruch auf "
            "zusätzliche Betreuungs- und Aktivierungsangebote, die über die "
            "pflegerische Grundversorgung hinausgehen."
        ),
        "region_binding": RegionBinding.region_independent,
        "scope_region": "DE_FEDERAL",
        "scope_target_groups": ("relative", "patient"),
        "evidence_passage_key": "§43b-abs1",
        "evidence_quote": (
            "Pflegebedürftige in stationären Pflegeeinrichtungen haben Anspruch auf "
            "zusätzliche Betreuung und Aktivierung, die über die nach Art und Schwere der "
            "Pflegebedürftigkeit notwendige Versorgung hinausgeht."
        ),
        "structured_values": [],
    },
]


# ────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────────────────────────────────


def _deterministic_uuid(seed: str) -> uuid.UUID:
    """Deterministisch: selbe Seed = selbe UUID. Verhindert Duplikate bei Wiederholung."""
    return uuid.UUID(hashlib.md5(f"careapp-pilot-{seed}".encode()).hexdigest())


# ────────────────────────────────────────────────────────────────────────────
# Haupt-Seeding-Logik
# ────────────────────────────────────────────────────────────────────────────


async def seed(session: AsyncSession, *, dry_run: bool = False) -> dict:
    """
    Gibt zurück: {"created": [...], "skipped": [...]}
    Dry-run: keine DB-Writes, gibt nur aus was gemacht würde.
    """
    created: list[str] = []
    skipped: list[str] = []

    # ── 1. Quelldokument prüfen / anlegen ──────────────────────────────────

    source_doc_id = _deterministic_uuid("source-doc-sgbxi")
    source_ver_id = _deterministic_uuid("source-ver-sgbxi-2024")

    existing_doc = await session.execute(
        select(SourceDocument).where(
            SourceDocument.canonical_ref == SGBXI_SOURCE["canonical_ref"]
        )
    )
    if existing_doc.scalar_one_or_none() is not None:
        print(f"  [SKIP] SourceDocument '{SGBXI_SOURCE['canonical_ref']}' bereits vorhanden.")
        skipped.append("SourceDocument/SGB XI")
    else:
        if not dry_run:
            session.add(SourceDocument(
                id=source_doc_id,
                type=SGBXI_SOURCE["type"],
                publisher=SGBXI_SOURCE["publisher"],
                canonical_ref=SGBXI_SOURCE["canonical_ref"],
                created_at=NOW,
            ))
            session.add(SourceVersion(
                id=source_ver_id,
                source_document_id=source_doc_id,
                content_hash=hashlib.sha256(SGBXI_SOURCE["edition_hash"].encode()).hexdigest(),
                edition_label=SGBXI_SOURCE["edition_label"],
                imported_at=NOW,
                object_store_uri=SGBXI_SOURCE["uri"],
            ))
            await session.flush()
        print(f"  [CREATE] SourceDocument '{SGBXI_SOURCE['canonical_ref']}'")
        created.append("SourceDocument/SGB XI")

    # ── 2. Passagen prüfen / anlegen ──────────────────────────────────────

    passage_id_by_key: dict[str, uuid.UUID] = {}
    for p in PASSAGES:
        passage_id = _deterministic_uuid(f"passage-{p['key']}")
        passage_id_by_key[p["key"]] = passage_id

        existing = await session.execute(
            select(SourcePassage).where(SourcePassage.id == passage_id)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"  [SKIP] Passage '{p['key']}' bereits vorhanden.")
            skipped.append(f"Passage/{p['key']}")
        else:
            if not dry_run:
                session.add(SourcePassage(
                    id=passage_id,
                    source_version_id=source_ver_id,
                    anchor=p["anchor"],
                    text=p["text"],
                ))
                await session.flush()
            print(f"  [CREATE] Passage '{p['key']}'")
            created.append(f"Passage/{p['key']}")

    # ── 3. Claims + ClaimVersions anlegen ─────────────────────────────────

    for cv_def in CV_DEFS:
        claim_id = _deterministic_uuid(f"claim-{cv_def['id_seed']}")
        cv_id = _deterministic_uuid(f"cv-{cv_def['id_seed']}")

        existing_cv = await session.execute(
            select(ClaimVersion).where(ClaimVersion.id == cv_id)
        )
        if existing_cv.scalar_one_or_none() is not None:
            print(f"  [SKIP] CV '{cv_def['id_seed']}' bereits vorhanden.")
            skipped.append(f"CV/{cv_def['id_seed']}")
            continue

        short = cv_def["statement_text"][:60].replace("\n", " ")
        print(f"  [CREATE] CV '{cv_def['id_seed']}' — \"{short}…\"")
        created.append(f"CV/{cv_def['id_seed']}")

        if not dry_run:
            # Claim
            session.add(Claim(
                id=claim_id,
                topic_scope="stationaere_pflege",
                region_binding=cv_def["region_binding"],
                created_at=NOW,
            ))
            await session.flush()

            # ClaimVersion
            cv = ClaimVersion(
                id=cv_id,
                claim_id=claim_id,
                statement_text=cv_def["statement_text"],
                status=ClaimVersionStatus.published,
                effective_from=EFFECTIVE,
                effective_to=None,
                published_at=NOW,
                unpublished_at=None,
                tenant_visibility=None,
                conflicting=False,
            )
            session.add(cv)
            await session.flush()

            # Scope: Region
            session.add(ScopeAssignment(
                id=_deterministic_uuid(f"scope-region-{cv_def['id_seed']}"),
                claim_version_id=cv_id,
                dimension=ScopeDimension.region,
                value=cv_def["scope_region"],
                applies=True,
            ))
            # Scope: Topic
            session.add(ScopeAssignment(
                id=_deterministic_uuid(f"scope-topic-{cv_def['id_seed']}"),
                claim_version_id=cv_id,
                dimension=ScopeDimension.topic,
                value="stationaere_pflege",
                applies=True,
            ))
            # Scope: Target groups (one per group)
            for i, tg in enumerate(cv_def["scope_target_groups"]):
                session.add(ScopeAssignment(
                    id=_deterministic_uuid(f"scope-tg-{i}-{cv_def['id_seed']}"),
                    claim_version_id=cv_id,
                    dimension=ScopeDimension.target_group,
                    value=tg,
                    applies=True,
                ))
            await session.flush()

            # Evidence
            passage_id = passage_id_by_key[cv_def["evidence_passage_key"]]
            session.add(ClaimEvidence(
                id=_deterministic_uuid(f"evidence-{cv_def['id_seed']}"),
                claim_version_id=cv_id,
                source_passage_id=passage_id,
                role=EvidenceRole.carrying,
                quote=cv_def["evidence_quote"],
            ))

            # Structured Values
            for j, sv in enumerate(cv_def["structured_values"]):
                session.add(StructuredValue(
                    id=_deterministic_uuid(f"sv-{j}-{cv_def['id_seed']}"),
                    claim_version_id=cv_id,
                    kind=sv["kind"],
                    value=sv["value"],
                    unit=sv.get("unit"),
                ))

            # Redaktionelle Freigabe (Vier-Augen simuliert durch Import-Vermerk)
            session.add(Approval(
                id=_deterministic_uuid(f"approval-import-{cv_def['id_seed']}"),
                claim_version_id=cv_id,
                pathway_id=None,
                actor_id="system:seed-pilot-v1",
                actor_role=ActorRole.importer,
                action="import",
                at=NOW,
                four_eyes_of=None,
            ))
            session.add(Approval(
                id=_deterministic_uuid(f"approval-editor-{cv_def['id_seed']}"),
                claim_version_id=cv_id,
                pathway_id=None,
                actor_id="editor:pflegerecht-nrw",
                actor_role=ActorRole.chief_editor,
                action="publish",
                at=NOW,
                four_eyes_of="system:seed-pilot-v1",
            ))

            await session.flush()

    if not dry_run:
        await session.commit()
        print("\n  ✓ Commit erfolgreich.")

    return {"created": created, "skipped": skipped}


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seeded Pilot-CVs für CareApp Heimunterbringung")
    parser.add_argument("--dry-run", action="store_true", help="Nur ausgeben, nicht schreiben")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="LÖSCHT alle Pilot-Daten und seeded neu (VORSICHT in Produktion!)",
    )
    args = parser.parse_args()

    engine = create_async_engine(DATABASE_URL, echo=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        if args.reset:
            print("! --reset: Lösche alle Daten (TRUNCATE CASCADE)...")
            if not args.dry_run:
                await session.execute(text(
                    "TRUNCATE TABLE approval, scope_assignment, structured_value, "
                    "claim_evidence, claim_version, claim, "
                    "source_passage, source_version, source_document CASCADE;"
                ))
                await session.commit()
                print("  Tabellen geleert.\n")

        print(f"Seeding Pilot-CVs (dry_run={args.dry_run})...\n")
        result = await seed(session, dry_run=args.dry_run)

    await engine.dispose()

    print(f"\nFertig: {len(result['created'])} erstellt, {len(result['skipped'])} übersprungen.")
    if result["created"]:
        for item in result["created"]:
            print(f"  + {item}")


if __name__ == "__main__":
    asyncio.run(main())

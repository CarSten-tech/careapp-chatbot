"""
Typisierter Konversations-State, Graph-Konfiguration und Audit (Layer 4, §1.4 / §5 / §6).

Der State trennt strikt: Sitzungsmeta ⊥ Hypothesen ⊥ bestätigte Fakten ⊥ Evidenz
⊥ Ausgabe (D-Invarianten, T7). Nutzereingaben sind ausschließlich DATEN im State,
nie Steuerung des Graphen (T1).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from careapp.domain.coverage import CoverageResult
from careapp.domain.evidence_builder import EvidencePackage
from careapp.llm.composer import ComposerOutcome
from careapp.llm.port import LLMCallAudit, LLMCallBudget, LLMTouchpoint
from careapp.llm.schemas import ComposerResponse, ConfirmedFact, ScopeSafetyClassification
from careapp.llm.scope_safety import ScopeSafetyDecision


# ------------------------------------------------------------------ #
# Versions-Tripel, Auth-Kontext, Budgets, Policy                      #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class GraphVersionTriple:
    """Festgepinntes Tripel pro Konversation (§1.1). Steht im Audit."""

    graph_version: str
    prompt_set_version: str
    model_version: str


@dataclass(frozen=True)
class AuthContext:
    """
    Aus dem Auth-/Consent-System — NIEMALS aus der Nutzernachricht (T4).
    `RequestContext` wird serverseitig hieraus + bestätigten Fakten gebaut.
    """

    tenant_id: Optional[str]
    region_id: Optional[str]
    target_group_codes: tuple[str, ...]
    consent_granted: bool
    locale: str = "de"


@dataclass(frozen=True)
class SessionBudgets:
    """
    Schleifen-/Mengengrenzen (§4). Konkrete Werte sind eine offene menschliche
    Entscheidung (§8) — hier konservative Pilot-Defaults.
    """

    max_clarify_rounds: int = 2
    max_recompose: int = 1
    max_retrieval_passes: int = 1
    max_graph_steps: int = 24  # harte Schleifenbremse über den ganzen Graphen
    max_user_message_chars: int = 2000   # L4-4: Riesen-Input-/Injection-Schutz
    max_turns_per_session: int = 20      # L4-4: Flooding-Schutz pro Session


@dataclass(frozen=True)
class ScopePolicy:
    """
    Serverseitige, redaktionell gepflegte Scope-/Safety-Definition (nicht LLM).
    `topic_in_allowed_scope` ist im Pilot grob (der harte Scope-Gate ist die
    Eligibility downstream); `safety_notices` bildet freigegebene IDs → Text ab.

    `handoff_available` aktiviert den HumanHandoff-Pfad (L4-1). Auslöser,
    Empfänger, Datenumfang und Autorisierung sind offene Entscheidungen (§8) —
    im Pilot-Default deaktiviert (Degradation auf NoVerifiedInformation).
    `handoff_text` überschreibt den Default-Übergabehinweis.
    """

    topic_in_allowed_scope: bool = True
    confidence_floor: float = 0.5
    approved_safety_notice_ids: frozenset[str] = frozenset()
    safety_notices: dict[str, str] = field(default_factory=dict)
    handoff_available: bool = False   # Pilot-Default: Handoff noch nicht aktiviert
    handoff_text: Optional[str] = None  # None → Default-Text in human_handoff-Node


def _default_model_ids() -> dict[LLMTouchpoint, str]:
    # Kostenempfehlung (Layer 2 trägt die Sicherheit, modellunabhängig):
    # günstige Modelle für Klassifikation/Routing, Sonnet nur für die Ausformulierung.
    # Nur Audit-/Referenzlabels — der konkrete Anbieter ist die injizierte LLMClient (§6 offen).
    return {
        LLMTouchpoint.scope_safety: "claude-haiku-4-5",
        LLMTouchpoint.intent: "claude-haiku-4-5",
        LLMTouchpoint.clarify: "claude-haiku-4-5",
        LLMTouchpoint.retrieval_terms: "claude-haiku-4-5",
        LLMTouchpoint.compose: "claude-sonnet-4-6",
    }


def _default_budget() -> LLMCallBudget:
    # Platzhalter; Durchsetzungswerte = offene Entscheidung (§8).
    return LLMCallBudget(max_input_tokens=8000, max_output_tokens=1500, timeout_seconds=30.0)


@dataclass(frozen=True)
class GraphConfig:
    """Statische, versionierte Graph-Konfiguration. Wird ins Audit-Tripel übernommen."""

    graph_version: str = "graph-v1"
    prompt_set_version: str = "prompts-v1"
    model_version: str = "models-v1"
    model_ids: dict[LLMTouchpoint, str] = field(default_factory=_default_model_ids)
    budget: LLMCallBudget = field(default_factory=_default_budget)
    policy: ScopePolicy = field(default_factory=ScopePolicy)
    aspect_map: Optional[dict[str, list[str]]] = None  # None → Produktions-ASPECT_MAP
    retrieval_top_k: int = 5  # semantischer Recall: max. Claims je Aspekt fürs Komponieren

    @property
    def versions(self) -> GraphVersionTriple:
        return GraphVersionTriple(self.graph_version, self.prompt_set_version, self.model_version)


# ------------------------------------------------------------------ #
# Disposition + Audit                                                 #
# ------------------------------------------------------------------ #


class Disposition(str, Enum):
    presented = "presented"
    no_verified_information = "no_verified_information"
    safe_scope_response = "safe_scope_response"
    safety_notice = "safety_notice"
    human_handoff = "human_handoff"
    clarify = "clarify"  # Turn endet mit Rückfrage, wartet auf Nutzerantwort


@dataclass(frozen=True)
class NodeTrace:
    node: str
    tools_used: tuple[str, ...]
    outcome: str
    fail_closed: bool = False


@dataclass(frozen=True)
class ConsultationAudit:
    """
    Audit-/Trace-Referenzen je Lauf (§6). Ohne unnötige PII.

    Metering-Felder (total_*) sind None wenn ausschließlich FakeLLMClient
    verwendet wurde oder der Adapter keine Werte zurückgegeben hat.
    Sie werden pro Aufruf aus LLMCallAudit aggregiert (nur nicht-None-Werte).
    """

    session_id: uuid.UUID
    versions: GraphVersionTriple
    nodes_traversed: tuple[str, ...]
    tool_calls: tuple[str, ...]  # "node:tool"
    llm_calls: tuple[LLMCallAudit, ...]  # Prompt-/Modellversion + Metering je LLM-Node (§1.7)
    evidence_claim_version_ids: tuple[str, ...]
    validation_passed: Optional[bool]
    disposition: Optional[str]
    fallback_reason: Optional[str]
    # Aggregiertes Metering (L3-2 / L4-3 / Spec §6: "Laufzeit, Token, Kosten")
    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    total_latency_ms: Optional[int] = None


# ------------------------------------------------------------------ #
# Der typisierte State                                                #
# ------------------------------------------------------------------ #


@dataclass
class ConsultationState:
    # Sitzungsmeta
    session_id: uuid.UUID
    requested_at: datetime
    auth: AuthContext
    budgets: SessionBudgets

    # Eingabe (DATEN)
    latest_user_message: str = ""

    # LLM-1 — Scope/Safety
    safety_classification: Optional[ScopeSafetyClassification] = None
    scope_decision: Optional[ScopeSafetyDecision] = None

    # LLM-2 — Anliegen (Hypothesen ⊥ bestätigte Fakten)
    intent_hypotheses: tuple[str, ...] = ()
    confirmed_facts: tuple[ConfirmedFact, ...] = ()
    missing_information: tuple[str, ...] = ()
    resolved_intent: Optional[str] = None

    # Pathway-Pfad (D9–D11). `pathway_answers` ist der über Turns persistierte
    # Fortschritt: decision_node.code → answer_value. Typisiert, ohne Roh-PII —
    # damit checkpoint-fähig (§5). Das LLM bestimmt den Pathway NIE.
    active_pathway_id: Optional[uuid.UUID] = None
    current_step_id: Optional[uuid.UUID] = None
    current_step_question: Optional[str] = None
    pathway_complete: bool = False
    pathway_answers: dict[str, str] = field(default_factory=dict)
    retrieval_topic_focus: Optional[str] = None  # aus PathwayStep.topic_hint / Branch-Modifier

    # Evidenz
    coverage: Optional[CoverageResult] = None
    coverage_aspect_override: Optional[dict[str, list[str]]] = None  # Pathway-fokussierte Suche
    evidence_package: Optional[EvidencePackage] = None
    compose_topic_scope: Optional[str] = None  # topic_scope, mit dem der Validator erneut prüft

    # Ausgabe
    composer_outcome: Optional[ComposerOutcome] = None
    final_response: Optional[ComposerResponse] = None
    disposition: Optional[Disposition] = None
    fallback_reason: Optional[str] = None

    # Budget-Zähler (über Turns hinweg persistierbar)
    clarify_rounds_used: int = 0
    turns_this_session: int = 0  # L4-4: aus Checkpoint laden; extract_checkpoint erhöht um 1

    # Audit-Akkumulation
    trace: list[NodeTrace] = field(default_factory=list)
    llm_audits: list[LLMCallAudit] = field(default_factory=list)
    audit: Optional[ConsultationAudit] = None

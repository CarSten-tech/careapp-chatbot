"""
Node-Implementierungen (Layer 4, §3).

Jeder Node liest/schreibt den typisierten `ConsultationState` und gibt den Namen
des nächsten Nodes zurück (oder `END`). Die fachliche Arbeit delegiert jeder Node
an die fertigen Bausteine aus Layer 2/3 — die Orchestrierung steuert nur den
Ablauf, nie die fachliche Wahrheit (§0).

Milestone 4.1 deckt den **DECIDE_FREE-Pfad** ab. Bewusst gefolded für den Pilot:
- RetrieveCandidates/FilterEligibility/BuildEvidencePackage → in `EvaluateCoverage`
  (Layer 2 `compute_coverage` lädt published CVs, filtert Eligibility, baut Packages).
- ComposeAnswer + ValidateStatements → in `compose_grounded_response` (Composer
  behandelt seine Ausgabe als Behauptung und validiert sie via D8, fail-closed).
Pathways (ResolvePathway, Clarify-aus-PathwayStep) und LLM-4-Retrieval-Terms sind
Milestone 4.2.
"""

import dataclasses
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import selectinload

from careapp.db.models.pathway import (
    LifeSituation,
    LifeSituationPathway,
    PathwayStatus,
    PathwayStep,
)
from careapp.domain.coverage import ASPECT_MAP, CoverageGrade, compute_coverage
from careapp.domain.eligibility import RequestContext
from careapp.llm.channels import ThreeChannelPrompt
from careapp.llm.composer import compose_grounded_response
from careapp.llm.embeddings import embedding_to_pgvector
from careapp.llm.fallback import fallback_composer_response
from careapp.llm.port import LLMCallAudit, LLMRequest, LLMTouchpoint
from careapp.llm.schemas import (
    ClarifyingQuestion,
    ClarifyingQuestionBlock,
    ComposerResponse,
    FallbackBlock,
    IntentUnderstanding,
    ScopeSafetyClassification,
    enforce_block_allowlist,
)
from careapp.llm.scope_safety import (
    DeterministicSignals,
    SafetyDisposition,
    decide_scope_safety,
)
from careapp.orchestration.state import (
    ConsultationAudit,
    ConsultationState,
    Disposition,
    GraphConfig,
)
from careapp.orchestration.tools import Tool, ToolContext

# ------------------------------------------------------------------ #
# Node-Namen (statisch)                                               #
# ------------------------------------------------------------------ #

END = "END"
SESSION_START = "SessionStart"
CONSENT = "ConsentAndAccessCheck"
SAFETY = "SafetyCheck"
UNDERSTAND = "UnderstandConcern"
RESOLVE = "ResolvePathway"
CLARIFY = "Clarify"
BUILD_RETRIEVAL = "BuildRetrievalPlan"
COVERAGE = "EvaluateCoverage"
COMPOSE = "ComposeAnswer"
PRESENT = "PresentAnswer"
NO_VERIFIED = "NoVerifiedInformation"
SAFE_SCOPE = "SafeScopeResponse"
SAFETY_NOTICE = "ApprovedSafetyNotice"
HANDOFF_Q = "HandoffQ"
HANDOFF = "HumanHandoff"
SUMMARY = "Summary"

NodeFn = Callable[[ConsultationState, ToolContext, GraphConfig], Awaitable[str]]

# Pilot-Default-Prompts. Der echte, versionierte Prompt-Satz (prompt_set_version)
# ist eine redaktionelle Aufgabe; hier nur knappe, sichere Platzhalter.

# Domänen-Anker (gegen generisches Abdriften / Halluzination): jeder Touchpoint
# bleibt strikt in der Pflegeberatung. Themen außerhalb sind nicht Teil der Beratung.
_DOMAIN_ANCHOR = (
    "Kontext: Dies ist eine Pflegeberatung nach deutschem Sozialrecht (SGB XI — "
    "Pflegeversicherung, Pflegegrade, Pflegeleistungen, häusliche und stationäre "
    "Pflege). Bleibe AUSSCHLIESSLICH in dieser Domäne. Themen außerhalb der Pflege "
    "(z. B. Miet-, Steuer-, Arbeits- oder allgemeines Recht) gehören NICHT zu dieser "
    "Beratung und dürfen weder vorgeschlagen noch als Option angeboten werden."
)

_SAFETY_RULES = (
    f"{_DOMAIN_ANCHOR}\n"
    "Klassifiziere Scope und Sicherheit. Nur enumerierte Labels, kein Freitext, kein Fachwissen.\n"
    "requires_individual_eligibility_decision=true NUR, wenn eine verbindliche "
    "Einzelfall-Entscheidung über den konkreten Anspruch einer Person verlangt wird "
    "(z. B. 'Habe ich Anspruch auf Pflegegrad 3?', 'Bekomme ich 1800 € im Monat?', "
    "'Steht meiner Mutter vollstationäre Pflege zu?'). "
    "Allgemeine oder prozedurale Fragen sind KEINE Einzelfall-Entscheidung und damit "
    "false (z. B. 'Meine Mutter muss ins Heim, was muss ich tun?', 'Welche Leistungen "
    "gibt es bei stationärer Pflege?', 'Welche Pflegegrade gibt es?', 'Wie läuft eine "
    "Heimunterbringung ab?'). Im Zweifel zwischen allgemein und Einzelfall: allgemein (false)."
)
_CLARIFY_RULES = (
    f"{_DOMAIN_ANCHOR}\n"
    "Formuliere eine kurze Rückfrage zu genau den fehlenden, fachlich nötigen Angaben "
    "INNERHALB der Pflegeberatung. Biete niemals Themen oder Antwortoptionen außerhalb "
    "der Pflege an. Keine versteckte fachliche Voraussetzung."
)


def _intent_rules(cfg: GraphConfig) -> str:
    """Intent-Prompt mit redaktionellem Vokabular (ASPECT_MAP-Schlüssel als
    einzige Quelle der Wahrheit). Das LLM ordnet auch umgangssprachliche Eingaben
    einem bekannten Anliegen-Code zu — die autoritative Auswahl bleibt serverseitig."""
    amap = cfg.aspect_map if cfg.aspect_map is not None else ASPECT_MAP
    codes = ", ".join(sorted(amap.keys())) or "(keine)"
    return (
        f"{_DOMAIN_ANCHOR}\n"
        "Überführe die Eingabe in eine schemavalidierte Interpretation. "
        "Keine Fachantwort; keine Hypothese als Fakt.\n"
        f"Bekannte Anliegen-Codes (intent_hypotheses): [{codes}]. "
        "Ordne das Anliegen des Nutzers — auch bei ungenauer, umgangssprachlicher oder "
        "nur sinngemäßer Formulierung — dem passenden Code zu und nimm ihn in "
        "intent_hypotheses auf. Beispiel: 'Meine Mutter muss ins Heim', 'Oma kommt ins "
        "Pflegeheim', 'wir brauchen einen Heimplatz' → 'heimunterbringung'. "
        "Wenn das Anliegen klar einem Code entspricht und keine zwingend nötige Angabe "
        "fehlt, setze missing_information=[] und recommended_next_action=proceed_to_retrieval. "
        "Demografische Angaben (Alter, Wohnort, konkrete Person, Bundesland) sind für "
        "allgemeine Informationsfragen NICHT erforderlich — behandle sie nicht als "
        "fehlend. missing_information nur füllen, wenn die Angabe fachlich zwingend "
        "nötig ist, um überhaupt eine geprüfte Aussage zuzuordnen. "
        "Erfinde keine Codes außerhalb der genannten Liste."
    )

SAFE_SCOPE_TEXT = "Dazu kann ich im Rahmen dieser Beratung nichts Geprüftes beitragen."

# Pilot-Platzhalter; produktiver Text = offene Entscheidung (§8 / HANDOVER.md OD-05+).
_DEFAULT_HANDOFF_TEXT = (
    "Für Ihre Anfrage können wir leider keine geprüfte Antwort bereitstellen. "
    "Wir empfehlen Ihnen, eine Fachberatungsstelle oder zuständige Behörde zu kontaktieren."
)


# ------------------------------------------------------------------ #
# Helfer                                                              #
# ------------------------------------------------------------------ #


def _request_context(state: ConsultationState, topic_scope: str) -> RequestContext:
    """T4-kritisch: RequestContext stammt aus dem Auth-Kontext, NIE aus der Nachricht."""
    return RequestContext(
        requested_at=state.requested_at,
        region_id=state.auth.region_id,
        target_group_codes=state.auth.target_group_codes,
        tenant_id=state.auth.tenant_id,
        topic_scope=topic_scope,
        locale=state.auth.locale,
    )


def _llm_request(
    state: ConsultationState,
    cfg: GraphConfig,
    touchpoint: LLMTouchpoint,
    system_rules: str,
    schema: type,
) -> LLMRequest:
    return LLMRequest(
        prompt=ThreeChannelPrompt(
            system_rules=system_rules,
            task=f"Verarbeite die Eingabe für Touchpoint {touchpoint.value}.",
            user_input=state.latest_user_message,
        ),
        response_schema=schema,
        audit=LLMCallAudit(
            touchpoint=touchpoint,
            prompt_version=cfg.prompt_set_version,
            model_id=cfg.model_ids[touchpoint],
        ),
        budget=cfg.budget,
    )


def _compile_audit(state: ConsultationState, cfg: GraphConfig) -> ConsultationAudit:
    nodes_traversed = tuple(t.node for t in state.trace)
    tool_calls = tuple(f"{t.node}:{tool}" for t in state.trace for tool in t.tools_used)
    cv_ids: tuple[str, ...] = ()
    if state.evidence_package is not None:
        cv_ids = tuple(sorted(str(i) for i in state.evidence_package.eligible_ids))
    validation_passed = None
    if state.composer_outcome is not None and state.composer_outcome.validation is not None:
        validation_passed = state.composer_outcome.validation.passed

    # Aggregiertes Metering (§6: "Laufzeit, Token, Kosten"). Nur nicht-None-Werte.
    calls = tuple(state.llm_audits)
    inp = [a.input_tokens for a in calls if a.input_tokens is not None]
    out = [a.output_tokens for a in calls if a.output_tokens is not None]
    cost = [a.cost_usd for a in calls if a.cost_usd is not None]
    lat = [a.latency_ms for a in calls if a.latency_ms is not None]

    return ConsultationAudit(
        session_id=state.session_id,
        versions=cfg.versions,
        nodes_traversed=nodes_traversed,
        tool_calls=tool_calls,
        llm_calls=calls,
        evidence_claim_version_ids=cv_ids,
        validation_passed=validation_passed,
        disposition=state.disposition.value if state.disposition else None,
        fallback_reason=state.fallback_reason,
        total_input_tokens=sum(inp) if inp else None,
        total_output_tokens=sum(out) if out else None,
        total_cost_usd=round(sum(cost), 8) if cost else None,
        total_latency_ms=sum(lat) if lat else None,
    )


# ------------------------------------------------------------------ #
# Nodes                                                               #
# ------------------------------------------------------------------ #


async def session_start(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    # L4-4: Input-Größenlimit — Riesen-Input-/Injection-Schutz
    if len(state.latest_user_message) > state.budgets.max_user_message_chars:
        state.fallback_reason = (
            f"input_too_large:{len(state.latest_user_message)}"
            f">{state.budgets.max_user_message_chars}"
        )
        return NO_VERIFIED
    # L4-4: Per-Session-Rate-Limit — Flooding-Schutz
    if state.turns_this_session >= state.budgets.max_turns_per_session:
        state.fallback_reason = (
            f"rate_limit_exceeded:{state.turns_this_session}"
            f">={state.budgets.max_turns_per_session}"
        )
        return NO_VERIFIED
    return CONSENT


async def consent_and_access(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    tools.auth()  # Auth-/Consent-Kontext lesen (liegt typisiert im State, aus Auth — T4)
    if not state.auth.consent_granted:
        return SAFE_SCOPE
    return SAFETY


async def safety_check(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    result = tools.llm().complete_structured(
        _llm_request(state, cfg, LLMTouchpoint.scope_safety, _SAFETY_RULES, ScopeSafetyClassification)
    )
    state.llm_audits.append(result.audit)
    classification = (
        result.parsed if result.ok and isinstance(result.parsed, ScopeSafetyClassification) else None
    )
    state.safety_classification = classification

    tools.safety_notice()  # Fähigkeit, freigegebene safety_notice-Bausteine zu prüfen
    signals = DeterministicSignals(
        topic_in_allowed_scope=cfg.policy.topic_in_allowed_scope,
        confidence_floor=cfg.policy.confidence_floor,
        approved_safety_notice_ids=cfg.policy.approved_safety_notice_ids,
    )
    decision = decide_scope_safety(classification, signals)
    state.scope_decision = decision

    if decision.disposition == SafetyDisposition.proceed:
        return UNDERSTAND
    if decision.disposition == SafetyDisposition.safety_notice:
        return SAFETY_NOTICE
    # out_of_scope ODER safe_fallback (Unsicherheit/Parsefehler) → konservativ
    state.fallback_reason = decision.reason
    return SAFE_SCOPE


async def understand_concern(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    result = tools.llm().complete_structured(
        _llm_request(state, cfg, LLMTouchpoint.intent, _intent_rules(cfg), IntentUnderstanding)
    )
    state.llm_audits.append(result.audit)
    if not (result.ok and isinstance(result.parsed, IntentUnderstanding)):
        state.fallback_reason = "intent_parse_error"
        return NO_VERIFIED  # §7: keine Annahme des Anliegens

    intent = result.parsed
    state.intent_hypotheses = intent.intent_hypotheses
    state.confirmed_facts = intent.confirmed_facts
    state.missing_information = intent.missing_information

    # Deterministisches Mapping intent → coverage-key. Das LLM bestimmt NICHT,
    # welcher Intent aktiv ist (es schlägt nur Hypothesen vor).
    amap = cfg.aspect_map if cfg.aspect_map is not None else ASPECT_MAP
    state.resolved_intent = next((h for h in intent.intent_hypotheses if h in amap), None)

    return RESOLVE  # Pathway-Auflösung entscheidet DECIDE_PATH vs. DECIDE_FREE


def _decide_free(state: ConsultationState) -> str:
    """DECIDE_FREE (kein passender Pathway): Kontext ausreichend?"""
    if state.resolved_intent is None or state.missing_information:
        return CLARIFY
    return BUILD_RETRIEVAL


@dataclass(frozen=True)
class _PathwayPosition:
    open_step: Optional[PathwayStep]
    topic_focus: Optional[str]


def _next_open_step(pathway: LifeSituationPathway, answers: dict[str, str]) -> _PathwayPosition:
    """
    Folgt den Antwort-Zweigen deterministisch ab dem Einstiegsschritt. Gibt den
    ersten unbeantworteten Schritt zurück (oder None bei Pathway-Ende) plus den
    Suchfokus aus topic_hint / terminalem retrieval_scope_modifier.
    """
    if not pathway.steps:
        return _PathwayPosition(None, None)
    steps_by_id = {s.id: s for s in pathway.steps}
    current: Optional[PathwayStep] = min(pathway.steps, key=lambda s: s.step_order)
    last_topic: Optional[str] = None
    while current is not None:
        last_topic = current.topic_hint or last_topic
        code = current.decision_node.code
        if code not in answers:
            return _PathwayPosition(current, current.topic_hint or last_topic)
        branch = next((b for b in current.branches if b.answer_value == answers[code]), None)
        if branch is None or branch.next_step_id is None:
            focus = None
            if branch is not None and branch.retrieval_scope_modifier:
                focus = branch.retrieval_scope_modifier.get("topic_scope")
            return _PathwayPosition(None, focus or last_topic)
        current = steps_by_id.get(branch.next_step_id)
    return _PathwayPosition(None, last_topic)


async def resolve_pathway(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    """
    Deterministisches Mapping resolved_intent → LifeSituation.code → published Pathway.
    Liest NUR published Pathways. Das LLM bestimmt nicht, welcher Pathway aktiv ist.
    """
    if state.resolved_intent is None:
        return _decide_free(state)

    session = tools.db()
    life_situation = (
        await session.execute(
            select(LifeSituation)
            .where(LifeSituation.code == state.resolved_intent)
            .options(
                selectinload(LifeSituation.pathways)
                .selectinload(LifeSituationPathway.steps)
                .selectinload(PathwayStep.decision_node),
                selectinload(LifeSituation.pathways)
                .selectinload(LifeSituationPathway.steps)
                .selectinload(PathwayStep.branches),
            )
        )
    ).scalar_one_or_none()

    if life_situation is None:
        return _decide_free(state)  # keine Lebenslage → freier Pfad

    published = [p for p in life_situation.pathways if p.status == PathwayStatus.published]
    if not published:
        return _decide_free(state)

    pathway = max(published, key=lambda p: p.version)
    state.active_pathway_id = pathway.id

    position = _next_open_step(pathway, state.pathway_answers)
    if position.open_step is None:
        state.pathway_complete = True
        state.retrieval_topic_focus = position.topic_focus
        return BUILD_RETRIEVAL  # Pathway vollständig → Suche/Antwort

    state.current_step_id = position.open_step.id
    state.current_step_question = position.open_step.decision_node.question_template_de
    state.retrieval_topic_focus = position.topic_focus
    return CLARIFY  # nächster offener PathwayStep


async def build_retrieval_plan(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    """
    Deterministischer Retrieval-Plan-Anteil. Nutzt den Pathway-Fokus
    (`topic_hint` / `retrieval_scope_modifier`) zur Suchfokussierung des
    Coverage-Aspekts. LLM-4-Term-Vorschläge + echter Index folgen; Status-/
    Mandanten-/Regions-/Gültigkeitsfilter bleiben immer serverseitig.
    """
    if state.retrieval_topic_focus:
        state.coverage_aspect_override = {state.resolved_intent or "": [state.retrieval_topic_focus]}
    return COVERAGE


async def clarify(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    # Pathway-Pfad: feste, redaktionell freigegebene Frage (kein freies Fragen).
    # Durch die endliche Pathway-Struktur begrenzt — nicht durch das Clarify-Budget.
    if state.active_pathway_id is not None and state.current_step_question is not None:
        state.final_response = ComposerResponse(
            blocks=(ClarifyingQuestionBlock(question_text=state.current_step_question),)
        )
        state.disposition = Disposition.clarify
        return SUMMARY

    # Freier Pfad: durch max_clarify_rounds begrenzt (§4). Obergrenze → HandoffQ.
    if state.clarify_rounds_used >= state.budgets.max_clarify_rounds:
        state.fallback_reason = "max_clarify_rounds_exceeded"
        return HANDOFF_Q

    result = tools.llm().complete_structured(
        _llm_request(state, cfg, LLMTouchpoint.clarify, _CLARIFY_RULES, ClarifyingQuestion)
    )
    state.llm_audits.append(result.audit)
    if not (result.ok and isinstance(result.parsed, ClarifyingQuestion)):
        state.fallback_reason = "clarify_parse_error"
        return NO_VERIFIED

    question = result.parsed
    state.clarify_rounds_used += 1
    state.final_response = ComposerResponse(
        blocks=(ClarifyingQuestionBlock(question_text=question.question_text),)
    )
    state.disposition = Disposition.clarify
    return SUMMARY  # Turn endet mit Rückfrage; Nutzerantwort startet den nächsten Turn


async def _semantic_rank_package(session, embedder, query: str, package, top_k: int):
    """Semantischer Recall NACH den Eligibility-Filtern: rangiert die bereits
    erlaubten Evidence-Items nach Nähe zur Frage und behält die top_k.

    Sicherheits-Invarianten:
    - reduziert NUR `items` (was der Composer sieht) — `eligible_ids` (die
      Erlaubnis-Menge des Validators) bleibt unverändert.
    - erlaubte Claims OHNE Embedding werden NIE verworfen (nur ans Ende sortiert).
    - jeder Fehler im Recall lässt das Package unverändert (fail-open NUR auf der
      Recall-Seite — die Erlaubnis bleibt fail-closed).
    """
    items = package.items
    if embedder is None or len(items) <= top_k:
        return package
    all_ids = [it.claim_version_id for it in items]
    try:
        qvec = embedding_to_pgvector(embedder.embed_query(query))
        stmt = text(
            "SELECT id FROM claim_version "
            "WHERE id IN :ids AND embedding IS NOT NULL "
            "ORDER BY embedding <=> (:q)::vector"
        ).bindparams(bindparam("ids", expanding=True))
        rows = (await session.execute(stmt, {"ids": all_ids, "q": qvec})).all()
    except Exception:  # noqa: BLE001 — Recall-Problem darf die Antwort nicht verhindern
        return package
    embedded_ranked = [r[0] for r in rows]
    if not embedded_ranked:
        return package
    embedded_set = set(embedded_ranked)
    kept = embedded_ranked[:top_k] + [i for i in all_ids if i not in embedded_set]
    by_id = {it.claim_version_id: it for it in items}
    return dataclasses.replace(package, items=tuple(by_id[i] for i in kept if i in by_id))


async def evaluate_coverage(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    session = tools.db()
    ctx_base = _request_context(state, topic_scope=state.resolved_intent or "")
    # Pathway-Fokus (falls gesetzt) verengt die Aspektkarte; sonst Default/Config.
    aspect_map = state.coverage_aspect_override or cfg.aspect_map
    result = await compute_coverage(
        session, ctx_base, state.resolved_intent or "", aspect_map=aspect_map
    )
    state.coverage = result

    if result.grade == CoverageGrade.insufficient:
        state.fallback_reason = "coverage_insufficient"
        return HANDOFF_Q

    # Pilot: ein Aspekt je Intent → genau ein abgedecktes Package wählen.
    # (Multi-Aspekt-Komposition mit getrenntem topic_scope je Aussage = Milestone 4.2.)
    aspect = sorted(result.covered_aspects)[0]
    package = result.packages[aspect]
    # Semantischer Recall: erlaubte Claims nach Frage-Nähe rangieren, top_k behalten.
    # Coverage-Entscheidung ist hier bereits gefallen und bleibt davon unberührt.
    package = await _semantic_rank_package(
        session, tools.embedder(), state.latest_user_message, package, cfg.retrieval_top_k
    )
    state.evidence_package = package
    state.compose_topic_scope = aspect
    return COMPOSE


async def compose_answer(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    session = tools.db()
    client = tools.llm()
    ctx = _request_context(state, topic_scope=state.compose_topic_scope or "")
    outcome = await compose_grounded_response(
        session=session,
        client=client,
        ctx=ctx,
        evidence_package=state.evidence_package,
        user_input=state.latest_user_message,
        confirmed_facts=state.confirmed_facts,
        model_id=cfg.model_ids[LLMTouchpoint.compose],
        budget=cfg.budget,
    )
    state.composer_outcome = outcome
    state.llm_audits.append(outcome.audit)

    if outcome.used_fallback:
        state.fallback_reason = outcome.fallback_reason
        return NO_VERIFIED  # Validator nicht bestanden → fail-closed (§7)
    return PRESENT


async def present_answer(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    tools.audit()
    # Defense-in-depth: Output-Block-Allowlist erneut serverseitig erzwingen (T11/T12).
    blocks = enforce_block_allowlist(state.composer_outcome.response.blocks)
    state.final_response = ComposerResponse(blocks=blocks)
    state.disposition = Disposition.presented
    return SUMMARY


async def no_verified_information(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    state.final_response = fallback_composer_response()
    state.disposition = Disposition.no_verified_information
    return SUMMARY


async def safe_scope_response(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    state.final_response = ComposerResponse(blocks=(FallbackBlock(text=SAFE_SCOPE_TEXT),))
    state.disposition = Disposition.safe_scope_response
    return SUMMARY


async def approved_safety_notice(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    tools.safety_notice()
    notice_id = state.scope_decision.safety_notice_id if state.scope_decision else None
    text = cfg.policy.safety_notices.get(notice_id) if notice_id else None
    if text is None:
        state.fallback_reason = "safety_notice_lookup_failed"
        return NO_VERIFIED  # §7: Lookup-Ausfall → konservativ, keine modellgenerierte Sicherheitsaussage
    state.final_response = ComposerResponse(blocks=(FallbackBlock(text=text),))
    state.disposition = Disposition.safety_notice
    return SUMMARY


async def handoff_q(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    """
    Deterministischer Entscheidungspunkt: Handoff verfügbar? (§8 / L4-1).
    `handoff_available` ist eine redaktionelle / betriebliche Entscheidung in
    `ScopePolicy` — im Pilot-Default False (Degradation auf NoVerifiedInformation).
    """
    if cfg.policy.handoff_available:
        return HANDOFF
    return NO_VERIFIED


async def human_handoff(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    """
    Kontrollierte Übergabe an eine Fachberatungsstelle (L4-1, §8).
    Auslöser, Empfänger, Datenumfang und Autorisierung sind offene Entscheidungen;
    der Pilot liefert nur den Übergabehinweis an die UI.
    Bei Ausfall des Übergabe-Prozesses (Exception) → fail-closed durch graph.py.
    """
    tools.handoff()
    text = cfg.policy.handoff_text or _DEFAULT_HANDOFF_TEXT
    state.final_response = ComposerResponse(blocks=(FallbackBlock(text=text),))
    state.disposition = Disposition.human_handoff
    return SUMMARY


async def summary(state: ConsultationState, tools: ToolContext, cfg: GraphConfig) -> str:
    tools.audit()
    state.audit = _compile_audit(state, cfg)
    return END


# ------------------------------------------------------------------ #
# Registry: Name → (Allowlist, Funktion)                              #
# ------------------------------------------------------------------ #

NODE_ALLOWLIST: dict[str, frozenset[Tool]] = {
    SESSION_START: frozenset(),
    CONSENT: frozenset({Tool.auth_read}),
    SAFETY: frozenset({Tool.llm, Tool.safety_notice_lookup}),
    UNDERSTAND: frozenset({Tool.llm}),
    RESOLVE: frozenset({Tool.db_read}),
    CLARIFY: frozenset({Tool.llm}),
    BUILD_RETRIEVAL: frozenset(),
    COVERAGE: frozenset({Tool.db_read, Tool.embed}),
    COMPOSE: frozenset({Tool.llm, Tool.db_read}),
    PRESENT: frozenset({Tool.audit_write}),
    NO_VERIFIED: frozenset(),
    SAFE_SCOPE: frozenset(),
    SAFETY_NOTICE: frozenset({Tool.safety_notice_lookup}),
    HANDOFF_Q: frozenset(),
    HANDOFF: frozenset({Tool.handoff_write}),
    SUMMARY: frozenset({Tool.audit_write}),
}

NODE_FNS: dict[str, NodeFn] = {
    SESSION_START: session_start,
    CONSENT: consent_and_access,
    SAFETY: safety_check,
    UNDERSTAND: understand_concern,
    RESOLVE: resolve_pathway,
    CLARIFY: clarify,
    BUILD_RETRIEVAL: build_retrieval_plan,
    COVERAGE: evaluate_coverage,
    COMPOSE: compose_answer,
    PRESENT: present_answer,
    NO_VERIFIED: no_verified_information,
    SAFE_SCOPE: safe_scope_response,
    SAFETY_NOTICE: approved_safety_notice,
    HANDOFF_Q: handoff_q,
    HANDOFF: human_handoff,
    SUMMARY: summary,
}

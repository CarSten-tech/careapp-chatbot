"""
Statischer Graph + Fail-Closed-Runner (Layer 4, §1 / §2 / §7).

Die Kanten sind FEST definiert (`ALLOWED_EDGES`). Ein Node kann nur zu einer
deklarierten Folge-Node springen; jeder andere Rückgabewert ist ein
Graph-Integritätsfehler und degradiert fail-closed (verteidigt T1: Nutzereingabe
ändert den Graphen nie).

Fail-Closed-Leitsatz (§7): JEDER Fehler — Exception, nicht erlaubtes Tool,
illegale Kante, Schritt-Obergrenze — endet in der sicheren Fallback-Antwort,
nie in einer freien Modellantwort.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from careapp.llm.fallback import fallback_composer_response
from careapp.llm.port import LLMClient
from careapp.orchestration.nodes import (
    BUILD_RETRIEVAL,
    CLARIFY,
    COMPOSE,
    CONSENT,
    COVERAGE,
    END,
    HANDOFF,
    HANDOFF_Q,
    NO_VERIFIED,
    NODE_ALLOWLIST,
    NODE_FNS,
    PRESENT,
    RESOLVE,
    SAFE_SCOPE,
    SAFETY,
    SAFETY_NOTICE,
    SESSION_START,
    SUMMARY,
    UNDERSTAND,
    _compile_audit,
)
from careapp.orchestration.state import (
    AuthContext,
    ConsultationState,
    Disposition,
    GraphConfig,
    NodeTrace,
    SessionBudgets,
)
from careapp.orchestration.tools import ToolContext

# Statische Kanten (Milestone 4.1: DECIDE_FREE-Pfad + 4.2: Pathway + Welle 3: HumanHandoff).
ALLOWED_EDGES: dict[str, frozenset[str]] = {
    SESSION_START: frozenset({CONSENT, NO_VERIFIED}),  # NO_VERIFIED: L4-4 Guard
    CONSENT: frozenset({SAFETY, SAFE_SCOPE}),
    SAFETY: frozenset({UNDERSTAND, SAFE_SCOPE, SAFETY_NOTICE}),
    UNDERSTAND: frozenset({RESOLVE}),
    RESOLVE: frozenset({CLARIFY, BUILD_RETRIEVAL}),
    CLARIFY: frozenset({SUMMARY, NO_VERIFIED, HANDOFF_Q}),
    BUILD_RETRIEVAL: frozenset({COVERAGE}),
    COVERAGE: frozenset({COMPOSE, HANDOFF_Q}),
    COMPOSE: frozenset({PRESENT, NO_VERIFIED}),
    PRESENT: frozenset({SUMMARY}),
    NO_VERIFIED: frozenset({SUMMARY}),
    SAFE_SCOPE: frozenset({SUMMARY}),
    SAFETY_NOTICE: frozenset({SUMMARY, NO_VERIFIED}),
    HANDOFF_Q: frozenset({HANDOFF, NO_VERIFIED}),
    HANDOFF: frozenset({SUMMARY, NO_VERIFIED}),
    SUMMARY: frozenset({END}),
}


def new_state(
    *,
    auth: AuthContext,
    latest_user_message: str,
    requested_at: datetime,
    budgets: Optional[SessionBudgets] = None,
    session_id: Optional[uuid.UUID] = None,
    clarify_rounds_used: int = 0,
    pathway_answers: Optional[dict[str, str]] = None,
    turns_this_session: int = 0,
) -> ConsultationState:
    """
    Initialer State für einen Konversationsturn. Eingabe ist DATEN, nie Steuerung.

    `pathway_answers`, `clarify_rounds_used` und `turns_this_session` tragen den
    Fortschritt über Turns hinweg — der Aufrufer persistiert sie als typisierten
    Checkpoint und reicht sie beim nächsten Turn wieder herein.
    """
    return ConsultationState(
        session_id=session_id or uuid.uuid4(),
        requested_at=requested_at,
        auth=auth,
        budgets=budgets or SessionBudgets(),
        latest_user_message=latest_user_message,
        clarify_rounds_used=clarify_rounds_used,
        pathway_answers=dict(pathway_answers) if pathway_answers else {},
        turns_this_session=turns_this_session,
    )


def _fail_closed(
    state: ConsultationState,
    node: str,
    tools: Optional[ToolContext],
    exc: BaseException,
    cfg: GraphConfig,
) -> None:
    """Globale Sicherheitsnetz-Degradation: sichere Fallback-Antwort + Audit."""
    used = tuple(sorted(t.value for t in tools.used)) if tools is not None else ()
    state.trace.append(
        NodeTrace(
            node=node,
            tools_used=used,
            outcome=f"FAIL_CLOSED:{type(exc).__name__}",
            fail_closed=True,
        )
    )
    if state.fallback_reason is None:
        state.fallback_reason = f"fail_closed:{type(exc).__name__}: {exc}"
    state.final_response = fallback_composer_response()
    state.disposition = Disposition.no_verified_information
    state.audit = _compile_audit(state, cfg)


async def run_consultation(
    state: ConsultationState,
    *,
    session: AsyncSession,
    llm: LLMClient,
    config: Optional[GraphConfig] = None,
) -> ConsultationState:
    """
    Führt einen Konversationsturn durch den statischen Graphen.

    Gibt den State mit `final_response` (immer UI-sicher), `disposition` und
    `audit` zurück. Wirft NICHT — jeder Fehler wird zur sicheren Fallback-Antwort.
    """
    cfg = config or GraphConfig()
    current = SESSION_START

    for _ in range(state.budgets.max_graph_steps):
        tools = ToolContext(current, NODE_ALLOWLIST[current], session, llm)
        try:
            nxt = await NODE_FNS[current](state, tools, cfg)
        except Exception as exc:  # noqa: BLE001 — jeder Node-Fehler → fail-closed (§7)
            _fail_closed(state, current, tools, exc, cfg)
            return state

        state.trace.append(
            NodeTrace(
                node=current,
                tools_used=tuple(sorted(t.value for t in tools.used)),
                outcome=nxt,
            )
        )

        if nxt == END:
            return state

        # Statische Kante erzwingen: ein undeklarierter Sprung ist ein Integritätsfehler.
        if nxt not in ALLOWED_EDGES.get(current, frozenset()):
            _fail_closed(state, current, tools, RuntimeError(f"illegal edge {current}->{nxt}"), cfg)
            return state

        current = nxt

    # Schritt-Obergrenze überschritten → harte Schleifenbremse, fail-closed.
    _fail_closed(state, current, None, RuntimeError("max_graph_steps exceeded"), cfg)
    return state

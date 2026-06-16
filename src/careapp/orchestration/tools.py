"""
Tool-Allowlist pro Node (Layer 4, §1.3 / §3 + DoD).

Jeder Node erhält einen `ToolContext`, der NUR die ihm zugewiesenen Fähigkeiten
freigibt. Der Zugriff auf eine nicht freigegebene Fähigkeit löst `ToolNotAllowed`
aus — serverseitig erzwungen, nicht durch Konvention. Kein Node hat dadurch
SQL-/Web-/Freigabezugriff; ein LLM-Node, der nicht `db_read` in seiner Allowlist
hat, kann den Wissensbestand strukturell nicht abfragen.
"""

from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from careapp.llm.port import LLMClient


class Tool(str, Enum):
    """Typisierte serverseitige Fähigkeiten. Bewusst grobgranular, aber trennscharf."""

    auth_read = "auth_read"                    # Auth-/Consent-Kontext lesen
    llm = "llm"                                # schema-erzwungener LLM-Port
    embed = "embed"                            # Embedding-Port (semantischer Recall)
    db_read = "db_read"                        # lesende Domain-Queries (Evidence/Coverage/Validator)
    safety_notice_lookup = "safety_notice_lookup"  # freigegebene safety_notice-Bausteine
    audit_write = "audit_write"                # Trace/Audit schreiben
    handoff_write = "handoff_write"            # Übergabe-Prozess (eigene Autorisierung, L4-1)


class ToolNotAllowed(RuntimeError):
    """Ein Node hat eine nicht in seiner Allowlist enthaltene Fähigkeit angefordert."""


@dataclass
class ToolContext:
    """
    Begrenzt die Fähigkeiten eines Nodes auf seine Allowlist. `used` protokolliert
    die tatsächlich genutzten Tools für das Audit (§6).
    """

    node_name: str
    allowed: frozenset[Tool]
    _session: AsyncSession
    _llm: LLMClient
    _embedder: object | None = None
    used: set[Tool] = field(default_factory=set)

    def _require(self, tool: Tool) -> None:
        if tool not in self.allowed:
            raise ToolNotAllowed(
                f"Node {self.node_name!r} darf Tool {tool.value!r} nicht nutzen "
                f"(Allowlist: {sorted(t.value for t in self.allowed)})"
            )
        self.used.add(tool)

    def llm(self) -> LLMClient:
        self._require(Tool.llm)
        return self._llm

    def embedder(self) -> object | None:
        """Embedding-Port für den semantischen Recall. None → semantik deaktiviert
        (graceful: das Retrieval fällt auf das bisherige Verhalten zurück)."""
        self._require(Tool.embed)
        return self._embedder

    def db(self) -> AsyncSession:
        self._require(Tool.db_read)
        return self._session

    def auth(self) -> None:
        """Markiert Auth-Read; der Auth-Kontext liegt bereits typisiert im State."""
        self._require(Tool.auth_read)

    def safety_notice(self) -> None:
        self._require(Tool.safety_notice_lookup)

    def audit(self) -> None:
        self._require(Tool.audit_write)

    def handoff(self) -> None:
        """Markiert die Nutzung des Übergabe-Prozesses; Auslöser/Empfänger = offene Entscheidung (§8)."""
        self._require(Tool.handoff_write)

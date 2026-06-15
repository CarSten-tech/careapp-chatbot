"""
Layer 4 — Conversation-Orchestrierung.

Verkettet die deterministischen Bausteine aus Layer 2 (`evidence_builder`,
`coverage`, `validator`) und die LLM-Berührungspunkte aus Layer 3 (`scope_safety`,
`composer` über den `LLMClient`-Port) zu einem **statischen, versionierten Graphen**.

Grundsätze (Architektur §1):
- Der Graph ist statisch definiert; Nutzereingabe ändert ihn NIE (T1).
- Jeder Node hat eine serverseitig erzwungene Tool-Allowlist.
- Jeder Fehler degradiert fail-closed Richtung sichere Antwort, nie zu freier Modellantwort.

Bewusste Architekturentscheidung: Die Engine ist schlank und ohne schwere
Fremdabhängigkeit (LangGraph ist in der Spec nur *vorgeschlagen*). Die Knoten und
Kanten bilden 1:1 einen LangGraph-`StateGraph` ab; die Adoption von LangGraph
bleibt eine offene Infrastrukturentscheidung (analog zur LLM-Anbieterwahl, §6).
"""

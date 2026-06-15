"""
Layer 3 — LLM-Schichten (Verträge, Drei-Kanal-Prompt, Threat-Kontrollen).

Anbieter-agnostisch: Der konkrete LLM-Anbieter ist eine offene, menschliche
Entscheidung (Architektur §6). Der Laufzeitkern spricht nur gegen den Port
(`careapp.llm.port.LLMClient`). Ein Referenz-Adapter für Anthropic Claude liegt
in `anthropic_adapter.py` und wird per Default empfohlen, ist aber austauschbar.
"""

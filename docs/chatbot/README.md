# CareApp – Chatbot-Architektur

Verbindliche Architekturübergabe für den Chatbot-Teil mit agentischem
Datenbankwissen. Diese Dokumente beschreiben den **Zielentwurf**, nicht eine
bereits implementierte Lösung. Nachfolgende Agenten dürfen die festgelegten
Schichtgrenzen und Invarianten nicht unterlaufen.

## Zentrale Regel

> Die KI führt das Gespräch. Die Wissensbasis liefert den Inhalt.
> Programmregeln kontrollieren die Verwendung. Menschen tragen die Verantwortung.
>
> **Sicherheitsziel:** Unbelegte, ungültige oder unzulässige fachliche
> Modellinhalte dürfen die Nutzeroberfläche nicht erreichen.

## Schichten und Lesereihenfolge

| Layer | Dokument | Status | Inhalt |
|---|---|---|---|
| 1 + 2 | [Wissensmodell & Kontrollkern](architecture-knowledge-and-control-core.md) | Accepted | Versioniertes Datenmodell (Identität vs. Fassung, Provenienz, Lifecycle) und deterministischer Kern (Eligibility-Filter, Evidence Builder, Coverage, Post-Generation-Validator). Enthält das Entscheidungslog D1–D8. |
| 3 | [LLM-Schichten & Threat-Model](architecture-llm-layers-and-threat-model.md) | Accepted | Verträge für jeden LLM-Aufruf (LLM-1…6) und das Adversarial-Threat-Model (T1–T13) inkl. abgeleiteter neuer Pflichten. |
| 4 | [Conversation-Orchestrierung](architecture-orchestration.md) | Accepted | Statischer, versionierter Graph; Tool-Allowlist pro Node; Budgets/Schleifengrenzen; Checkpoints; Fail-Closed-Degradation; Audit-Trace. |
| 5 | [Evaluation & Pilot](architecture-evaluation-and-pilot.md) | Accepted | Synthetisches Golden Test Set (C1–C17), Metriken, harte/weiche Release-Gates, CI-Verankerung, Pilot-Eintritts-/Ausbaukriterien. |
| 6 | [API-Schicht & Clients](architecture-clients.md) | Accepted | FastAPI-Backend, Next.js Web-App (primärer Fokus), SwiftUI iOS-App (später). OpenAPI-Spec als Vertragsgrundlage. Auth-Middleware, Session-Middleware, Citation-UI, Accessibility. |

**Empfohlene Lesereihenfolge:** Layer 1+2 zuerst (alles baut darauf auf),
dann Layer 3, dann Layer 4, dann Layer 5.

**Übergabepunkt:** [HANDOVER.md](HANDOVER.md) — jederzeit kalt übernehmbarer Stand.

**Offene Entscheidungen:** [open-decisions.md](open-decisions.md) — OD-01–04 entschieden, OD-05–13 offen, OD-14–17 client-spezifisch (in [architecture-clients.md](architecture-clients.md) §5).
**Rollen & Berechtigungen:** [roles.md](roles.md) — Freigaberollen, Statusübergänge, Vier-Augen.

## Modellnutzung beim Weiterplanen

- Kern-/Sicherheitsentscheidungen (Datenmodell, Kontrollkern, LLM-Verträge,
  Threat-Model): **Opus 4.8, hoher Denkaufwand**.
- Ausformulierung (JSON-Schemas, DB-Constraints/Migrationen, Golden Test Set):
  **Sonnet 4.6, mittlerer Aufwand**.
- Boilerplate/Formatierung: **Haiku 4.5, niedriger Aufwand**.

## Offene Entscheidungen

Quer über alle Layer bewusst **nicht** technisch entschieden — gemeinsam mit
Product Owner, Fachredaktion, Datenschutz-, Rechts-, Security- und
Infrastruktur-Fachleuten zu klären. Siehe jeweils den Abschnitt
„Offene Entscheidungen“ der einzelnen Dokumente.

# CareApp – Rollen & Berechtigungen

**Status:** Accepted
**Letzte Aktualisierung:** 2026-06-13
**Gilt für:** Redaktionellen Workflow, Freigabeprozess, Administration.

---

## Grundsatz

Kein Service-, Modell-, Import- oder Batch-Account darf `approved` oder
`published` setzen. Diese Übergänge sind ausschließlich authentifizierten
menschlichen Akteuren mit einer der unten genannten Rollen vorbehalten.

Vier-Augen-Prinzip ist **immer** aktiv: Die Person, die `approved` setzt, und
die Person, die `published` setzt, müssen verschieden sein (`four_eyes_of ≠
approver_id`). Das wird als DB-Constraint beim Statusübergang erzwungen.

---

## Rollenübersicht

| Rolle | Beschreibung | Darf |
|---|---|---|
| `author` | Erstellt Wissens­entwürfe aus geprüften Quell­passagen | Dokumente einsehen; ClaimVersion-Entwürfe anlegen (`draft → in_review`) |
| `editor` | Fach­liche Erst­prüfung und erste Freigabe | Alles von `author`; ClaimVersions inhaltlich prüfen; erste Freigabe (`in_review → approved`) |
| `chief_editor` | Abschließende Freigabe und Rückzug | Alles von `editor`; Veröffentlichung (`approved → published`, Vier-Augen); Rückzug (`published → withdrawn`); Ablösung (`published → superseded`) |
| `importer` | Technischer Dokument­import | Originaldokumente importieren (SourceDocument, SourceVersion, SourcePassage anlegen); keine Claim-Arbeit |
| `regional_editor` | Wie `editor`, jedoch auf zugewiesene Region(en) beschränkt | Wie `editor`, nur für ClaimVersions der eigenen Region(en) |
| `org_admin` | Organisations- und Nutzer­verwaltung | Nutzer anlegen/deaktivieren, Rollen zuweisen; **keine** fachliche Freigabe |
| `system_admin` | Technische Administration | Infrastruktur, Deployments, Konfiguration; **keine** fachliche Freigabe |

---

## Statusübergänge je Rolle

| Übergang | Wer darf | Vier-Augen |
|---|---|---|
| `draft → in_review` | `author`, `editor`, `chief_editor` | nein |
| `in_review → approved` | `editor`, `chief_editor`, `regional_editor` (im Scope) | nein |
| `approved → published` | `chief_editor` | **ja** — muss anderer Mensch als der `approved`-Setzer sein |
| `published → withdrawn` | `chief_editor` | nein (Einzelentscheidung mit Audit) |
| `published → superseded` | `chief_editor` | nein (wird durch neue ClaimVersion ausgelöst) |
| `* → conflicting` (Flag) | System (deterministisch) + `chief_editor` kann auflösen | — |

---

## Was kein Account darf (absolut)

- `approved` oder `published` über API-Key, Service-Account oder Modell-Call setzen.
- Einen Statusübergang ohne authentifizierten `actor_id` in der `Approval`-Tabelle.
- Die `four_eyes_of`-Prüfung clientseitig umgehen — sie wird serverseitig erzwungen.

---

## Notizen für die Implementierung

- `actor_role` ist ein DB-Enum mit genau den oben genannten Werten.
- `regional_editor` bekommt eine Zuordnungstabelle `editor_region_scope
  (actor_id, region_id)` — die Eligibility-Prüfung beim Übergang liest daraus.
- Für den Pilot (Kreis Neuss / Düsseldorf) reichen zunächst: `author`,
  `editor`, `chief_editor`, `importer`. Die weiteren Rollen können mit dem
  ersten Mandanten-Onboarding aktiviert werden.

# CareApp Chatbot – Offene Entscheidungen

**Zweck:** Alle offenen Entscheidungen aus Layer 1–5 an einem Ort, in
entscheidungsreifer Form. Keine dieser Fragen wird durch die KI entschieden.
Jede Entscheidung hier beeinflusst konkret das Datenmodell, die Testdaten oder
die Implementierungsreihenfolge.

**Stand:** 2026-06-13 (OD-01 bis OD-04 entschieden)

---

## Legende

| Symbol | Bedeutung |
|---|---|
| 🔴 | Blocker — blockiert Implementierung direkt |
| 🟡 | Wichtig — beeinflusst Schnittstellen oder Tests |
| 🟢 | Kann nach MVP-Start entschieden werden |

---

## OD-01 ✅ Vier-Augen-Prinzip bei Freigabe — ENTSCHIEDEN

**Entscheidung:** Vier-Augen-Prinzip ist **immer** aktiv. Der Übergang
`approved → published` verlangt zwingend eine zweite, vom Erstfreigeber
verschiedene Person (`four_eyes_of ≠ approver_id`). DB-Constraint erzwungen.

---

## OD-02 ✅ Freigaberollen — ENTSCHIEDEN

**Entscheidung:** Rollen wurden definiert. Vollständige Spezifikation:
[`roles.md`](roles.md).

Kurz: `author` (Entwurf) → `editor` (erste Freigabe) → `chief_editor`
(Veröffentlichung, Vier-Augen). Zusätzlich: `importer`, `regional_editor`,
`org_admin`, `system_admin`. Für den Pilot aktiv: die ersten vier.

---

## OD-03 ✅ Pilot-Lebenslage — ENTSCHIEDEN

**Entscheidung:** Erste Pilot-Lebenslage: **„Meine Mutter muss ins Heim"**
(stationäre Pflege / Heimunterbringung).

**Daraus abgeleitete `aspect_map`-Einträge** (redaktionell zu befüllen):
- Pflegegrad-Voraussetzungen für stationäre Pflege
- Heimsuche und Einrichtungen (region-spezifisch: Kreis Neuss / Düsseldorf)
- Kosten und Eigenanteil
- Leistungen der Pflegekasse (stationär, §§ 43, 43a SGB XI)
- Sozialhilfe bei Kostenunterdeckung (§ 61 SGB XII)
- Antragstellung und Verfahren
- Kurzzeitpflege als Überbrückung
- Beratungsstellen regional

---

## OD-04 ✅ Pilotregion — ENTSCHIEDEN

**Entscheidung:** Pilotregion ist **Kreis Neuss / Düsseldorf** (Nordrhein-Westfalen).

Alle `ScopeAssignment`-Zeilen mit `dimension=region` erhalten als Wert eine
interne Regions-ID, die Kreis Neuss und Stadt Düsseldorf abbildet (konkrete
ID-Vergabe beim Persistenzschema).

---

## OD-05 🟡 Anonyme vs. kontobasierte Nutzung

**Frage:** Können Bürger den Chatbot anonym nutzen, oder ist eine
(Leicht-)Registrierung nötig?

**Warum es wichtig ist:** Beeinflusst `consent_state`-Modellierung im
ConsultationState, Session-Verknüpfung, Datenschutz-Grundlage und Handoff-Prozess
(wer bekommt eine Übergabe, wenn kein Konto existiert?).

**Wer entscheidet:** Product Owner, Datenschutz, Recht.

---

## OD-06 🟡 Aufbewahrungsfristen und Löschung

**Frage:** Wie lange werden Conversation-Checkpoints, Audit-Traces und
Telemetrie-Daten aufbewahrt? Welche Lösch-Automatik ist nötig?

**Warum es wichtig ist:** Beeinflusst Checkpoint-Schema (Layer 4 §5) und
ob Traces PII-frei gehalten werden können oder ob technische Löschroutinen
gebaut werden müssen.

**Wer entscheidet:** Datenschutz, Recht, Infrastruktur.

---

## OD-07 🟡 Produktiver LLM-Anbieter und Hosting

**Frage:** Welches LLM (Anbieter, Modell-ID) wird produktiv eingesetzt?
Wo wird die Anwendung gehostet (Cloud-Anbieter, Region, On-Premise)?

**Warum es wichtig ist:** Beeinflusst Auftragsverarbeitungsvertrag,
Datenfluss-Dokumentation, Prompt-/Modellversionierung und ob Modell-Antworten
in Deutschland/EU verbleiben müssen.

**Wer entscheidet:** Infrastruktur, Datenschutz, Recht, Product Owner.

---

## OD-08 🟡 Quellenhierarchie und Konfliktauflösung

**Frage:** Wenn zwei ClaimVersionen mit `ClaimRelation:conflicts_with` beide
eligible sind — welche hat Vorrang? (z. B. Bundesrecht > Landesrecht >
eigener Expertentext, oder nach Aktualität, oder Eskalation zur Redaktion?)

**Warum es wichtig ist:** Der Evidence Builder (Layer 2 §4.2) muss wissen,
was mit `conflicting`-Paaren passiert: blockieren, ranken oder eskalieren.

**Wer entscheidet:** Fachredaktion, ggf. Rechtsberatung.

---

## OD-09 🟡 Schwellwerte der weichen Evaluation-Gates

**Frage:** Ab welchem Wert gelten Fallback Precision, Retrieval Recall,
Handoff Appropriateness, Citation Coverage/Correctness als „bestanden"?

**Warum es wichtig ist:** Ohne diese Werte sind die CI-Reports vorhanden, aber
es gibt keinen Release-Trigger für weiche Qualitätsziele (Layer 5 §3).

**Wer entscheidet:** Product Owner, Fachredaktion, Qualitätsverantwortliche.

---

## OD-10 🟡 Ausgestaltung des menschlichen Handoffs

**Frage:** Was passiert bei `HumanHandoff` konkret? Wohin wird übergeben
(Beratungsstelle, internes Team, Rückruf-Formular)? Welche Daten gehen mit?
Wer autorisiert den Datentransfer?

**Warum es wichtig ist:** Der Handoff-Node (Layer 4 §3) ist ein eigener
Prozess mit eigener Autorisierung — er kann nicht ohne dieses Wissen
implementiert werden.

**Wer entscheidet:** Product Owner, Datenschutz, Recht, operative Partner.

---

## OD-11 🟢 Einfache vs. leichte Sprache

**Frage:** Soll die App neben Standardsprache auch „Leichte Sprache" (nach
BITV/DIN) anbieten? Im MVP oder erst später?

**Warum es nachrangig ist:** Kann als `locale`-Parameter nachgerüstet werden,
ohne das Kernmodell zu ändern. Beeinflusst aber Composer-Prompts und redaktionelle
Prüfpflichten.

**Wer entscheidet:** Product Owner, Fachredaktion, Barrierefreiheits-Fachleute.

---

## OD-12 🟢 MVP-Sprachen

**Frage:** Nur Deutsch im MVP? Oder von Anfang an weitere Sprachen
(z. B. Türkisch, Arabisch, Englisch)?

**Wer entscheidet:** Product Owner, ggf. kommunale Partner.

---

## OD-13 🟢 Regulatorische Einordnung

**Frage:** Fällt CareApp unter eine spezifische Regulierung (z. B. als
Medizinprodukt nach MDR, als KI-System nach EU AI Act)? Welche Konformitäts-
nachweise sind nötig?

**Wer entscheidet:** Recht, ggf. Regulatory-Fachleute, Product Owner.

---

## Zusammenfassung: Reihenfolge für Entscheidungsgespräche

Für den Implementierungsstart von Layer 1 werden **OD-01 bis OD-04** benötigt.
Ohne Pilot-Lebenslagen (OD-03) und Pilotregion (OD-04) können keine synthetischen
Testdaten erstellt werden; ohne Freigaberollen (OD-01, OD-02) kann das
Approval-Constraint nicht gebaut werden.

**Empfohlene Gesprächsreihenfolge:**
1. Product Owner + Fachredaktion: OD-01, OD-02, OD-03, OD-04
2. Datenschutz + Recht: OD-05, OD-06, OD-07, OD-10
3. Infrastruktur: OD-07
4. Alle Fachverantwortlichen: OD-08, OD-09
5. Später: OD-11, OD-12, OD-13

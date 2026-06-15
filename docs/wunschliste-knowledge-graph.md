# Wunschliste: Knowledge-Graph-Explorer

Stand: 2026-06-14  
Status: Konzept / noch nicht implementiert

---

## Ziel

Der Knowledge Graph macht das gesamte redaktionelle Wissen der CareApp sichtbar —
als interaktives Netz aus Fachaussagen, Quelldokumenten und ihren Verknüpfungen.
Redakteure und Administratoren sollen auf einen Blick sehen, was existiert,
wie es zusammenhängt, und wo Lücken oder Widersprüche sind.

---

## Was angezeigt wird

### Knoten (Nodes)

| Typ | Farbe | Bedeutung |
|---|---|---|
| Quelldokument | Grün | SGB XI, BMG-Broschüre, GKV-Richtlinie etc. |
| Fachaussage (published) | Lila | Freigegebene, aktive Aussage |
| Fachaussage (draft) | Grau | Entwurf, noch nicht freigegeben |
| Fachaussage (superseded) | Orange | Abgelöst, nicht mehr aktiv |
| Pathway | Blau | Lebenslagen-Pfad (z.B. „Mutter ins Heim") |

### Kanten (Verbindungen)

| Typ | Stil | Bedeutung |
|---|---|---|
| `requires` | durchgezogen grau | Aussage B setzt Aussage A voraus |
| `supersedes` | gestrichelt orange | Neue Version löst alte ab |
| `conflicts_with` | gestrichelt rot | Zwei Aussagen widersprechen sich |
| `applies_with` | gepunktet blau | Gilt gemeinsam mit einer anderen Aussage |
| `evidence` | gepunktet grün | Quelldokument belegt diese Aussage |

---

## Gewünschte Funktionen

### Basis-Interaktion

- **Zoom**: Mausrad oder Pinch-to-Zoom (Mobilgerät)
- **Verschieben**: Klicken und Ziehen auf leeren Flächen
- **Drehen**: Optional, 3D-Rotation des gesamten Graphen
- **Zurücksetzen**: Button „Ansicht zurücksetzen" auf Ausgangszoom

### Knoten anklicken

Klick auf einen Knoten öffnet ein Seitenpanel mit:
- Vollständiger Fachaussage / Dokumenttitel
- Status und Vertrauensstufe
- Liste aller Verbindungen mit Relationstyp
- Direkt-Link in den Admin zum Bearbeiten
- Wenn Quelldokument: Anzahl der Passagen und belegten Aussagen

### Filter und Suche

- Nach **Status** filtern (nur published / alle inkl. draft)
- Nach **Thema** filtern (stationaere_pflege, ambulante_pflege usw.)
- Nach **Quelle** filtern (nur SGB XI, nur BMG-Broschüren usw.)
- **Freitextsuche**: Knoten mit passendem Text hervorheben
- **Zeitstrahl**: Ansicht zu einem bestimmten Datum (was war published am 01.01.2024?)

### Hervorhebung

- Klick auf Knoten: nur dieser Knoten und alle direkt verbundenen bleiben sichtbar, Rest wird ausgegraut
- Hover über Kante: zeigt Relationstyp als Tooltip
- Widersprüche (`conflicts_with`) werden automatisch rot hervorgehoben
- Verwaiste Knoten (keine Verbindungen) werden markiert

### Übersicht-Modus

- Cluster-Ansicht: Knoten werden nach Thema gruppiert (jeder Themenkreis = eine Wolke)
- Zeigt auf einen Blick: welche Themen gut abgedeckt sind, welche dünn

### Export

- Screenshot des aktuellen Graphen als PNG
- Export als JSON (für externe Weiterverarbeitung)

---

## Was schon vorhanden ist (Datenmodell)

Das Datenmodell unterstützt den Graphen bereits vollständig:

```
ClaimVersion     ←→ ClaimRelation ←→ ClaimVersion
     ↑                                    ↑
ClaimEvidence                      (requires, supersedes,
     ↑                              conflicts_with, ...)
SourcePassage
     ↑
SourceVersion
     ↑
SourceDocument
```

Tabellen: `claim`, `claim_version`, `claim_relation`, `claim_evidence`,
`source_document`, `source_version`, `source_passage`

Fehlend im Modell:
- `authority_rank` auf `source_document` (Vertrauensstufe 1–5)
- `source_url` auf `source_document` (für Web-Quellen)
- `valid_until` auf `source_version` (Ablaufdatum für Broschüren)

---

## Technische Umsetzungsideen

### Variante A: Im Admin eingebettet (empfohlen für Pilot)
- Seite `/admin/graph` in der bestehenden Next.js-App
- D3.js Force-Directed Graph (bereits als Demo vorhanden)
- Daten kommen von einem neuen FastAPI-Endpunkt `GET /api/v1/admin/graph`
  der alle Knoten + Kanten als JSON liefert
- Aufwand: ~3–5 Tage

### Variante B: Eigenständige App (für spätere Phase)
- Separate React-App mit 3D-Graph-Bibliothek (z.B. `react-force-graph-3d`)
- Echte 3D-Rotation, bessere Performance bei 1000+ Knoten
- Aufwand: ~1–2 Wochen

### Variante C: Neo4j (bei sehr großem Wissensgraph)
- Wenn der Graph 10.000+ Knoten erreicht, lohnt sich eine native Graph-Datenbank
- Neo4j hat eine eingebaute Visualisierung (Neo4j Bloom)
- Migration von PostgreSQL → Neo4j wäre notwendig
- Aufwand: erheblich, erst bei Bedarf

---

## Neue FastAPI-Endpunkte (noch zu bauen)

```
GET /api/v1/admin/graph
    → { nodes: [...], edges: [...] }
    Query-Parameter: status, topic, source_id, date_as_of

GET /api/v1/admin/graph/node/{cv_id}
    → Knoten-Detail mit allen direkten Nachbarn
```

---

## Offene Fragen

1. Soll der Graph auch für Endnutzer sichtbar sein (vereinfachte Ansicht)?
   Oder nur intern für Redakteure?

2. Ab welcher Anzahl Knoten wird Performance ein Thema?
   (D3.js läuft gut bis ~500 Knoten, danach braucht es WebGL)

3. Soll die Visualisierung in Echtzeit aktualisieren wenn jemand im Admin
   eine neue Aussage freigibt? (WebSocket) Oder reicht manuelles Neu-Laden?

4. Gewünschte Sprache der Knoten-Labels: Deutsch oder technische Kürzel?

---

## Nächste Schritte (wenn bereit zum Bauen)

1. `authority_rank` + `source_url` + `valid_until` zur DB hinzufügen (Migration 0005)
2. `GET /api/v1/admin/graph` Endpunkt bauen
3. `/admin/graph` Seite in Next.js mit D3.js (Demo-Code bereits vorhanden)
4. Filter-UI und Seitenpanel implementieren
5. Variante B / C evaluieren wenn Datenmenge wächst

# CareApp – Architektur: API-Schicht & Clients (Layer 6)

**Status:** Accepted (Layer 6)
**Gültig für:** Chatbot-Teil mit agentischem Datenbankwissen
**Letzte Aktualisierung:** 2026-06-14
**Voraussetzungen:** Layer 1–5 (siehe [README](README.md)).
**Tech-Stack-Entscheidung:** Next.js (Web, primärer Fokus) + SwiftUI (iOS, später).

---

## 0. Geltungsbereich

Dieses Dokument beschreibt die **API-Schicht** (FastAPI) und die beiden
**Client-Anwendungen** (Next.js Web + SwiftUI iOS), die auf dem Chatbot-Kern
(Layer 1–5) aufsetzen. Es legt fest:

- wie der Kern nach außen exponiert wird (REST-API),
- wie Auth und Session zwischen Client und Kern fließen,
- wie die Web-App aufgebaut ist,
- wie die iOS-App aufgebaut sein wird (dokumentiert, noch nicht implementiert),
- welche Sicherheits- und Datenschutzgrenzen auf dieser Schicht gelten,
- welche Entscheidungen noch offen sind.

**Grundregel (T4 für die Client-Schicht):**
Der `AuthContext` (Mandant, Region, Zielgruppen, Einwilligung) wird **immer
serverseitig** aus dem validierten Auth-Token aufgebaut — niemals aus der
Nachricht, einem Query-Parameter oder einer Client-Assertion. Das LLM sieht
den AuthContext nur indirekt (als Filterergebnis); kein Client-seitiger Parameter
darf ihn überschreiben.

---

## 1. Systemübersicht

```
┌─────────────────────────────────────────┐
│          Nutzer / Browser / iPhone       │
└────────────┬──────────────┬─────────────┘
             │              │
    ┌─────────▼──┐    ┌──────▼──────┐
    │  Next.js   │    │  SwiftUI    │  (iOS, später)
    │  Web-App   │    │  iOS-App    │
    │  (Vercel)  │    │  (App Store)│
    └─────────┬──┘    └──────┬──────┘
             │              │
             │   HTTPS/TLS  │
             │              │
    ┌─────────▼──────────────▼─────────────┐
    │         FastAPI  (Python)             │
    │   POST /api/v1/chat                  │
    │   Auth-Middleware (JWT → AuthContext) │
    │   Session-Middleware (Checkpoint)     │
    └─────────────────┬────────────────────┘
                      │
    ┌─────────────────▼────────────────────┐
    │     CareApp-Kern (Layer 1–5)          │
    │  run_consultation() · CheckpointStore │
    │  Supabase PostgreSQL · AnthropicLLM   │
    └──────────────────────────────────────┘
```

---

## 2. API-Schicht (FastAPI)

### 2.1 Technologie-Wahl

**FastAPI** (Python 3.12, async, Pydantic v2, SQLAlchemy async).

Begründung:
- Kern ist Python → kein Sprachenwechsel, kein RPC-Overhead
- Automatische OpenAPI-Spec (OpenAPI 3.1) → Vertragsgrundlage für beide Clients
- Pydantic-Schemas aus dem Kern direkt als Request/Response-Modelle nutzbar
- Async-first: SQLAlchemy async + AnthropicLLMClient passen direkt rein

### 2.2 Endpunkte

#### `POST /api/v1/chat`

Hauptendpunkt — empfängt eine Nutzernachricht und gibt die geprüfte Antwort zurück.

**Request:**
```json
{
  "message": "Meine Mutter muss ins Heim — welche Leistungen gibt es?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

- `message`: Freitext (Nutzereingabe, DATEN — T1). Max. `max_user_message_chars` Zeichen
  (aktuell 2000, konfigurierbar — L4-4).
- `session_id`: optional. Fehlt bei erstem Turn → API erstellt neue Session.

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "disposition": "presented",
  "blocks": [
    {
      "type": "empathy",
      "text": "Das ist eine sehr belastende Situation."
    },
    {
      "type": "factual_statement",
      "text": "Bei Pflegegrad 2 oder höher besteht Anspruch auf vollstationäre Pflege ...",
      "claim_version_ids": ["a1b2c3d4-..."],
      "structured_values": [
        { "kind": "amount_eur", "value": "2005", "unit": "EUR" }
      ]
    }
  ],
  "audit_ref": "audit-uuid-...",
  "fallback_reason": null,
  "turn": 1
}
```

- `disposition`: `presented` | `no_verified_information` | `safe_scope_response` |
  `human_handoff` | `clarify`
- `blocks`: direkt aus `ComposerResponse.blocks` — clientseitig nicht interpretiert,
  nur gerendert. Typen: `empathy`, `factual_statement`, `clarifying_question`, `fallback`.
- `audit_ref`: UUID des `ConsultationAudit` — für spätere Nachverfolgung/Support.
- `fallback_reason`: gesetzt wenn kein Ergebnis (`null` im Normalfall).
- `turn`: Nummer des Gesprächszugs in dieser Session.

**HTTP-Status:**
- `200 OK` — immer, wenn der Kern eine Antwort produziert (auch Fallback).
- `400 Bad Request` — Validierungsfehler (Nachricht zu lang, fehlende Felder).
- `401 Unauthorized` — kein oder ungültiger Auth-Token.
- `429 Too Many Requests` — Rate-Limit überschritten (Infra-Ebene, vor dem Kern).
- `503 Service Unavailable` — Kern nicht erreichbar.

> **Niemals `500` mit Stack-Trace zur Client-Schicht.** Alle Fehler enden im
> sicheren Fallback (Layer 4 §7 Fail-Closed). Ist der Kern komplett nicht
> erreichbar, gibt die API `503` zurück — ohne interne Details.

#### `GET /api/v1/session/{session_id}/state`

Gibt den aktuellen (letzten) Checkpoint einer Session zurück — für den Client,
um nach einem Absturz/Reload die Session fortzusetzen.

**Response:**
```json
{
  "session_id": "...",
  "turn": 3,
  "clarify_rounds_used": 1,
  "pathway_progress": { "pflegegrad_bekannt": "true" }
}
```

Kein `latest_user_message`, kein Auth-Kontext (PII-frei, analog Checkpoint §5).

#### `DELETE /api/v1/session/{session_id}`

Löscht den Checkpoint. Nutzer startet neu.

#### `GET /api/v1/health`

Health-Check für Load-Balancer / Monitoring. Gibt `{"status": "ok"}` zurück.

### 2.3 Auth-Middleware

```
Eingehender Request
    │
    ▼
JWT validieren (Supabase Auth / eigener Auth-Provider)
    │
    ├─ ungültig → 401
    │
    ▼
AuthContext aufbauen (T4: aus Token-Claims, NIE aus Request-Body):
    tenant_id     = token["app_metadata"]["tenant_id"]
    region_id     = token["app_metadata"]["region_id"]
    target_groups = token["app_metadata"]["target_group_codes"]
    consent       = token["app_metadata"]["consent_granted"]
    locale        = token["app_metadata"]["locale"] ?? "de"
    │
    ▼
AuthContext in Request-State einbetten
→ Kern-Aufruf mit validiertem AuthContext
```

**Anonyme Sessions (OD-05 offen):**
Bis OD-05 entschieden: anonyme Sessions bekommen ein serverseitig generiertes
`session_id` ohne User-Bindung. Consent wird explizit am Anfang abgefragt und
als Flag im Cookie / Session gespeichert (nicht im JWT).
Authentifizierte Sessions binden `session_id` an die `user_id` im Token.

### 2.4 Session-Middleware

```python
# Vereinfachter Pseudocode — Muster für jeden Chat-Request
cp = await checkpoint_store.load(session_id)
state = new_state(
    auth=auth_context,
    latest_user_message=request.message,
    requested_at=now,
    session_id=cp.session_id if cp else None,
    clarify_rounds_used=cp.clarify_rounds_used if cp else 0,
    pathway_answers=cp.pathway_answers if cp else {},
    budgets=cp.budgets if cp else SessionBudgets(),
    turns_this_session=cp.turns_this_session if cp else 0,
)
state_out = await run_consultation(state, session=db, llm=llm_client)
await checkpoint_store.save(extract_checkpoint(state_out, cfg))
return build_response(state_out)
```

### 2.5 OpenAPI-Spec als Vertragsgrundlage

FastAPI generiert automatisch eine OpenAPI 3.1-Spec (`/openapi.json`).
Beide Clients leiten ihre Typen daraus ab:

- **TypeScript (Next.js):** `openapi-typescript` → generierte `api.d.ts`
- **Swift (iOS):** `swift-openapi-generator` → generierte Swift-Structs

Der Vertrag ist die Spec — nicht inoffizielle Absprachen zwischen Teams. Bei
Spec-Änderungen müssen beide Clients aktualisiert werden.

### 2.6 Sicherheit auf API-Ebene

| Anforderung | Umsetzung |
|---|---|
| TLS | Pflicht (Vercel / AWS ALB / Nginx terminiert) |
| CORS | Nur eigene Origins (Web-Domain + iOS-App via `null`-Origin-Sonderregel) |
| Rate Limiting | Infra-Ebene (Vercel Edge / AWS WAF) + Kern-Ebene (L4-4) |
| Input-Größe | HTTP-Limit (nginx `client_max_body_size`) + Kern-Guard (`max_user_message_chars`) |
| Auth-Token | Bearer-Token im `Authorization`-Header — niemals in der URL |
| Stack-Trace | Niemals im Response-Body. Nur in internen Logs (mit `audit_ref`) |
| Secrets | API-Keys (Anthropic, Supabase) nur server-seitig, nie im Client-Bundle |

---

## 3. Web-App (Next.js) — primärer Fokus

### 3.1 Technologie-Wahl

| Bereich | Wahl | Begründung |
|---|---|---|
| Framework | **Next.js 15 (App Router)** | SSR, Server Components, eingebaute Auth-Middleware, TypeScript-first |
| Sprache | **TypeScript** | Typsicherheit, API-Vertrag aus OpenAPI-Spec generierbar |
| Styling | **Tailwind CSS** | Utility-first, keine Laufzeit-Abhängigkeit, gute Accessibility-Unterstützung |
| Auth | **Supabase Auth** (Client SDK) | Bereits Supabase im Stack, JWT-Kompatibilität, anonyme Sessions möglich |
| API-Client | Generiert aus OpenAPI-Spec | Typsichere Calls, keine manuellen Typdefinitionen |
| Hosting | **Vercel** (empfohlen) | Next.js-nativ, Edge Middleware, keine Infra-Komplexität im MVP |
| Accessibility | WCAG 2.1 AA (Mindest) | Gesundheits-/Sozialberatung hat erhöhte Barrierefreiheitspflicht |

### 3.2 Verzeichnisstruktur (geplant)

```
apps/web/
├── app/
│   ├── layout.tsx              # Root Layout: Fonts, Providers, ARIA-Landmarks
│   ├── page.tsx                # Startseite / Onboarding
│   ├── chat/
│   │   ├── page.tsx            # Chat-Hauptseite (Server Component: Session-Restore)
│   │   └── [session_id]/
│   │       └── page.tsx        # Laufende Session (Client Component)
│   ├── api/
│   │   └── chat/
│   │       └── route.ts        # Next.js Route Handler → FastAPI Proxy
│   └── consent/
│       └── page.tsx            # Einwilligungsseite (vor erstem Chat)
├── components/
│   ├── chat/
│   │   ├── ChatContainer.tsx   # Zustandsloser Shell
│   │   ├── MessageList.tsx     # Liste aller Turns
│   │   ├── MessageBubble.tsx   # Eine Nachricht (Nutzer oder System)
│   │   ├── BlockRenderer.tsx   # Rendert OutputBlock-Typen
│   │   ├── FactualBlock.tsx    # factual_statement mit Citation-Tooltip
│   │   ├── FallbackBlock.tsx   # Fallback-Wortlaut
│   │   ├── ClarifyBlock.tsx    # Rückfrage mit optionalen Buttons
│   │   └── InputBar.tsx        # Texteingabe + Senden
│   ├── ui/                     # Design-System-Primitives (Button, Badge, …)
│   └── consent/
│       └── ConsentBanner.tsx   # DSGVO-Einwilligung
├── lib/
│   ├── api-client.ts           # Typsicherer Wrapper um FastAPI (aus OpenAPI gen.)
│   ├── session.ts              # Session-ID aus Cookie/localStorage lesen/setzen
│   └── auth.ts                 # Supabase Auth Helpers
├── middleware.ts               # Next.js Edge Middleware: Auth prüfen, Consent-Gate
└── types/
    └── api.d.ts                # Generiert aus FastAPI /openapi.json
```

### 3.3 Datenfluss (ein Chat-Turn)

```
Nutzer tippt Nachricht
    │
    ▼
InputBar.tsx sendet POST /api/chat (Next.js Route Handler)
    │
    ▼
Next.js middleware.ts:
  - JWT aus Cookie lesen
  - Consent-Flag prüfen → sonst Redirect zu /consent
  │
  ▼
Route Handler (api/chat/route.ts):
  - JWT validieren (Supabase Auth)
  - Session-ID aus Request lesen / neu generieren
  - POST an FastAPI /api/v1/chat weiterleiten (mit Bearer-Token)
  - NIEMALS Anthropic-API-Key oder DB-Credentials an den Browser
    │
    ▼
FastAPI (server-seitig):
  - AuthContext aus Token
  - Checkpoint laden / speichern
  - run_consultation() → Kern Layer 1–5
    │
    ▼
Route Handler gibt Response zurück
    │
    ▼
MessageList.tsx rendert neuen Turn
BlockRenderer.tsx wählt Komponente je Block-Typ:
  - "factual_statement" → FactualBlock (Text + Citation-Badge)
  - "clarifying_question" → ClarifyBlock (Text + optionale Buttons)
  - "fallback" → FallbackBlock (Hinweistext + Contact-Info)
  - "empathy" → einfacher Text
```

### 3.4 Consent-Gate (DSGVO)

Vor dem ersten Chat-Turn:
1. Nutzer sieht `/consent` — erklärt, was der Chatbot tut und nicht tut
2. Nutzer bestätigt aktiv (Checkbox + Button, kein Dark Pattern)
3. `consent_granted=true` wird im Session-Cookie gesetzt
4. Next.js Middleware leitet jeden Chat-Request ohne gültigen Consent auf `/consent` um
5. Der `AuthContext` bekommt `consent_granted=true` — der Kern akzeptiert den Turn

### 3.5 Citation-UI (Provenienz sichtbar)

Jede `factual_statement` zeigt einen zitierbaren Quellenhinweis:

```
┌─────────────────────────────────────────────────┐
│ Bei Pflegegrad 2+ besteht Anspruch auf voll-    │
│ stationäre Pflege nach § 43 SGB XI.             │
│                                                  │
│ [Quelle: SGB XI §43, Stand: Jan 2025] ⓘ        │
└─────────────────────────────────────────────────┘
```

- Klick auf `ⓘ` öffnet ein Overlay mit: Passage-Zitat, Dokument, Datum, `claim_version_id`
- Implementierung: `claim_version_id` → separater API-Call `GET /api/v1/citation/{id}`
- Kein Linking zu externen Seiten im MVP (Sicherheits-/Haftungsrisiko)

### 3.6 Accessibility (WCAG 2.1 AA)

| Anforderung | Umsetzung |
|---|---|
| Tastaturnavigation | Alle Interaktionen per Tastatur erreichbar |
| Screen Reader | ARIA-Labels auf allen dynamischen Inhalten, `aria-live` für neue Nachrichten |
| Kontrast | Mindest-4,5:1 (Text), 3:1 (UI-Elemente) |
| Schriftgröße | Kein `px`-Hardcoding, `rem`/`em` für skalierbare Schrift |
| Fokus-Indikator | Sichtbarer `:focus-visible`-Ring |
| Fehlermeldungen | Textuell, nicht nur farblich |

### 3.7 Sicherheitsregeln für den Next.js-Layer

- **API-Keys niemals im Browser.** Anthropic-Key und Supabase-Service-Key
  nur in Next.js Server Components / Route Handlers / Middleware — nie in
  Client Components (`"use client"`).
- **FastAPI-URL nicht im Client-Bundle** — Route Handler als Proxy, nie
  direkter Browser→FastAPI-Call.
- **Content Security Policy (CSP):** `default-src 'self'`, kein `unsafe-eval`,
  kein unkontrolliertes externe Skriptladen.
- **Session-ID:** im `HttpOnly`-Cookie (nicht `localStorage`) — verhindert
  XSS-Zugriff.
- **Kein Freitext-Rendering ohne Sanitisierung.** Alle `text`-Felder aus
  der API werden als Text gerendert (`textContent`), nie als HTML (`innerHTML`).

---

## 4. iOS-App (SwiftUI) — dokumentiert, später

### 4.1 Technologie-Wahl

| Bereich | Wahl | Begründung |
|---|---|---|
| Framework | **SwiftUI** | Native iOS-Patterns, Accessibility (VoiceOver, Dynamic Type) out-of-the-box |
| Sprache | **Swift 6** | Concurrency (async/await), strikte Typsicherheit |
| Networking | **URLSession** (async/await) | Kein Drittanbieter nötig, direkte Kontrolle |
| Auth | **Supabase Swift SDK** | Konsistent mit Web; JWT-Kompatibilität |
| API-Typen | Generiert aus OpenAPI-Spec | `swift-openapi-generator` → Swift-Structs |
| Token-Speicher | **Keychain** (via `KeychainAccess` oder direkt) | Sicher, kein `UserDefaults` für Secrets |
| Hosting | App Store | Standardpfad |

### 4.2 Kernarchitektur (geplant)

```
CareApp iOS
├── App/
│   └── CareAppApp.swift        # @main, Auth-State-Injection
├── Features/
│   ├── Onboarding/             # Einwilligung, ggf. Region-Auswahl
│   ├── Chat/
│   │   ├── ChatViewModel.swift # @Observable: Turns, Session, LadeZustand
│   │   ├── ChatView.swift      # SwiftUI View: ScrollView + InputBar
│   │   ├── MessageView.swift   # Ein Turn
│   │   └── BlockViews/         # Pro OutputBlock-Typ eine View
│   └── Citation/
│       └── CitationSheet.swift # Quellendetail als Sheet
├── Services/
│   ├── APIClient.swift         # URLSession-Wrapper, aus OpenAPI generiert
│   ├── AuthService.swift       # Supabase Auth
│   └── SessionService.swift    # Checkpoint/Session-ID in Keychain
└── Models/                     # Aus OpenAPI-Spec generiert
```

### 4.3 Besonderheiten iOS vs. Web

| Aspekt | Web (Next.js) | iOS (SwiftUI) |
|---|---|---|
| Auth-Token-Speicher | `HttpOnly`-Cookie | Keychain |
| Session-ID-Speicher | Cookie | Keychain / `@AppStorage` |
| Offline | Kein MVP-Ziel | Session-Wiederherstellung per Checkpoint |
| Accessibility | ARIA, WCAG | VoiceOver, Dynamic Type, nativ |
| Consent | Web-Seite `/consent` | Onboarding-Screen vor erstem Turn |
| Push-Notifications | Nicht geplant | Zukünftig: Handoff-Benachrichtigung |
| Face ID / Touch ID | N/A | Zukünftig: für Account-Login |

### 4.4 Implementierungsreihenfolge (wenn iOS startet)

1. API-Client aus OpenAPI-Spec generieren (`swift-openapi-generator`)
2. Supabase Auth SDK einbinden (anonyme Session zuerst)
3. Chat-ViewModel + Chat-View (Minimalversion)
4. BlockViews je Typ (factual, clarifying, fallback, empathy)
5. Citation-Sheet
6. Onboarding / Consent-Screen
7. Keychain-Integration für Session-ID
8. Accessibility-Audit (VoiceOver durchklicken)

---

## 5. Offene Entscheidungen (client-spezifisch)

### OD-14 🔴 Anonyme vs. kontobasierte Session-Persistenz (Web)

**Frage:** Kann der Nutzer ohne Konto den Chatbot nutzen und seine Session über
Browser-Tabs hinweg fortsetzen? Oder ist ein Login zwingend?

**Warum es wichtig ist:**
- Anonym: Session-ID im Cookie → bei Cookie-Löschen verloren. Keine Konto-Bindung.
- Konto: Session persistent, Handoff-Prozess möglich, aber Registrierungshürde.
- Beide Varianten sind technisch vorbereitet (Kern unterstützt `tenant_id=None`).

**Was jetzt schon gebaut werden kann:** Anonyme Sessions (Session-ID im Cookie,
kein Login-Screen). Die kontobasierte Variante kann später ergänzt werden.

**Wer entscheidet:** Product Owner, Datenschutz (siehe auch OD-05).

### OD-15 🟡 Streaming vs. Request/Response

**Frage:** Soll die API die Antwort als vollständigen JSON-Block liefern
(einfacher) oder als Server-Sent Events (SSE) streamen (bessere UX bei langen
Antworten)?

**Tradeoffs:**
- **JSON-Block:** einfach zu implementieren, keine Stream-Komplexität,
  aber Nutzer wartet ohne Feedback bis der Kern fertig ist (~2–5 Sekunden).
- **SSE:** Nutzer sieht, dass etwas passiert (Ladeanimation oder partieller Text),
  aber Kern muss Streaming unterstützen (aktuell nicht).

**MVP-Empfehlung:** JSON-Block + Skeleton-UI (Ladeanimation während Request läuft).
SSE als Erweiterung nach dem Pilot.

**Wer entscheidet:** Product Owner (UX-Priorität), Technik (Implementierungsaufwand).

### OD-16 🟡 Deployment-Ziel Web-App

**Frage:** Vercel (einfachster Weg für Next.js), AWS (Enterprise-Kontrolle,
EU-Region), oder self-hosted?

**Warum es wichtig ist:** DSGVO verlangt EU-Datenverarbeitung. Vercel EU-Region
(Frankfurt) ist verfügbar. AWS eu-central-1 (Frankfurt) ebenfalls. Self-hosted
maximale Kontrolle, höchster Betriebsaufwand.

**Empfehlung MVP:** Vercel (EU-Region) für die Next.js-App, Supabase (eu-central-1)
für die DB — beides bereits Frankfurt. Später Migration auf eigene Infra möglich.

**Wer entscheidet:** Infrastruktur, Datenschutz (OD-07 betrifft den Kern,
OD-16 betrifft nur das Web-Frontend).

### OD-17 🟢 Handoff-UI

**Frage:** Was sieht der Nutzer, wenn `disposition=human_handoff`? Nur Text
(Kontaktdaten einer Beratungsstelle), ein eingebettetes Formular, oder ein
Rückruf-Booking-Widget?

**MVP-Empfehlung:** Nur Text + Kontaktdaten der Beratungsstelle (Kreis Neuss /
Düsseldorf). Alles andere nach dem Pilot.

**Wer entscheidet:** Product Owner, operative Partner, Datenschutz (OD-10).

---

## 6. Definition of Done (Layer 6)

### 6.1 API-Schicht

- [ ] `POST /api/v1/chat` implementiert und getestet (Integration-Tests mit FakeLLM)
- [ ] `GET /api/v1/session/{id}/state` implementiert
- [ ] `DELETE /api/v1/session/{id}` implementiert
- [ ] Auth-Middleware: JWT → AuthContext (T4 gewährleistet)
- [ ] Session-Middleware: Checkpoint laden / speichern je Request
- [ ] OpenAPI-Spec generiert und versioniert
- [ ] Fehlerbehandlung: niemals Stack-Trace im Response-Body
- [ ] Health-Check-Endpunkt
- [ ] Integrationstests gegen echte Supabase-Instanz mit FakeLLMClient

### 6.2 Web-App (Next.js)

- [ ] Chat-Hauptflow: Nachricht senden → Antwort rendern (alle Block-Typen)
- [ ] Session-Persistenz: Reload → Chat fortsetzen
- [ ] Consent-Gate: kein Chat ohne Einwilligung
- [ ] Citation-UI: Quellenhinweis je `factual_statement`
- [ ] Fallback-UI: `disposition=no_verified_information` → klarer Hinweistext
- [ ] Handoff-UI: `disposition=human_handoff` → Kontaktdaten (Kreis Neuss)
- [ ] Clarify-UI: `disposition=clarify` → Frage + optionale Antwort-Buttons
- [ ] Accessibility-Audit (WCAG 2.1 AA): Tastatur, Screen Reader, Kontrast
- [ ] API-Keys niemals im Client-Bundle (überprüfbar via `next build` + Bundle-Analyse)
- [ ] CSP-Header gesetzt
- [ ] Session-ID im `HttpOnly`-Cookie

### 6.3 iOS-App (SwiftUI) — später

- [ ] Chat-Hauptflow (analog Web)
- [ ] Onboarding / Consent-Screen
- [ ] Keychain-Integration für Session-ID und Auth-Token
- [ ] VoiceOver-Audit bestanden
- [ ] Dynamic Type (alle Texte skalierbar)
- [ ] App-Store-Submission vorbereitet

---

## 7. Implementierungsreihenfolge Web-App

Empfohlene Reihenfolge für den ersten Pilot:

1. **FastAPI-Skeleton** — `POST /api/v1/chat` mit echtem `run_consultation()`-Aufruf,
   Dummy-Auth (Bearer-Token wird akzeptiert, AuthContext hardcoded für Pilot),
   Checkpoint-Middleware. Getestet mit FakeLLMClient.

2. **AnthropicLLMClient einbinden** — `uv sync --extra llm`, API-Key via Env-Var,
   erster echter End-to-End-Test mit echter Wissensbasis.

3. **Next.js-Projekt aufsetzen** — `npx create-next-app@latest`, App Router,
   TypeScript, Tailwind. TypeScript-Typen aus OpenAPI-Spec generieren.

4. **Chat-UI Kern** — `ChatContainer`, `MessageList`, `MessageBubble`, `InputBar`.
   POST gegen `/api/chat` Route Handler (Proxy zu FastAPI). Skeleton-Ladeanimation.

5. **BlockRenderer** — alle vier Block-Typen korrekt rendern.
   `factual_statement` mit Citation-Badge (Overlay kommt in Schritt 7).

6. **Consent-Gate** — `/consent`-Seite + Next.js Middleware.

7. **Session-Persistenz** — Session-ID im Cookie, Reload → Chat fortsetzen.

8. **Citation-UI** — `GET /api/v1/citation/{id}` + Overlay-Component.

9. **Handoff/Fallback-UI** — Klare Hinweistexte je Disposition.

10. **Accessibility-Audit** — ARIA, Tastatur, Kontrast, Screen Reader.

11. **Deployment auf Vercel (EU-Region)** — mit echter Supabase-Instanz
    (tbfzghhxeutbkbqubowp, eu-central-1) und echtem AnthropicLLMClient.

12. **Pilot-Eintrittsprüfung** — harte Gates mit echtem LLM bestehen (§3 aus Layer 5).

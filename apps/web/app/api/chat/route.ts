// Route Handler: Proxy zwischen Browser und FastAPI (§3.3 / §3.7).
// API-Keys und FastAPI-URL sind server-seitige Env-Vars — nie im Client-Bundle.
// Credentials: same-origin; Session-ID im HttpOnly-Cookie (§3.7).

import type { NextRequest } from "next/server";
import { cookies } from "next/headers";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.message !== "string") {
    return Response.json({ error: "invalid_request" }, { status: 400 });
  }

  // Session-ID aus Cookie lesen (HttpOnly — kein XSS-Zugriff)
  const cookieStore = await cookies();
  const cookieSessionId = cookieStore.get("careapp_session_id")?.value ?? null;
  const sessionId: string | null = body.session_id ?? cookieSessionId ?? null;

  const upstream = await fetch(`${FASTAPI_URL}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: body.message, session_id: sessionId }),
  }).catch(() => null);

  if (!upstream || !upstream.ok) {
    return Response.json({ error: "service_unavailable" }, { status: 503 });
  }

  const data = await upstream.json();

  // Session-ID als HttpOnly-Cookie persistieren
  const responseHeaders = new Headers({ "Content-Type": "application/json" });
  if (data.session_id) {
    responseHeaders.append(
      "Set-Cookie",
      `careapp_session_id=${data.session_id}; Path=/; HttpOnly; SameSite=Lax`
    );
  }

  return new Response(JSON.stringify(data), {
    status: 200,
    headers: responseHeaders,
  });
}

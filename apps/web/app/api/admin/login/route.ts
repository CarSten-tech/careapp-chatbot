// Login-Route: prüft Admin-Passwort gegen CAREAPP_ADMIN_TOKEN,
// setzt bei Erfolg httpOnly-Cookie.

import type { NextRequest } from "next/server";

export async function POST(request: NextRequest): Promise<Response> {
  const body = await request.json().catch(() => null);
  if (!body || typeof body.password !== "string") {
    return Response.json({ error: "invalid_request" }, { status: 400 });
  }

  const adminToken = process.env.CAREAPP_ADMIN_TOKEN ?? "";
  if (!adminToken) {
    return Response.json({ error: "admin_not_configured" }, { status: 503 });
  }

  if (body.password !== adminToken) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  const headers = new Headers({ "Content-Type": "application/json" });
  headers.append(
    "Set-Cookie",
    `careapp_admin_token=${adminToken}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400`
  );

  return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
}

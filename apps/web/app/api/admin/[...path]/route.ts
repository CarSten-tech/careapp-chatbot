// Proxy: leitet alle /api/admin/* Requests an FastAPI /api/v1/admin/* weiter.
// Admin-Token wird aus httpOnly-Cookie gelesen und als Bearer-Token gesetzt.

import type { NextRequest } from "next/server";
import { cookies } from "next/headers";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const upstreamPath = path.join("/");

  const cookieStore = await cookies();
  const token = cookieStore.get("careapp_admin_token")?.value;

  if (!token) {
    return Response.json({ error: "admin_unauthorized" }, { status: 401 });
  }

  const url = `${FASTAPI_URL}/api/v1/admin/${upstreamPath}${request.nextUrl.search}`;

  const headers: HeadersInit = {
    Authorization: `Bearer ${token}`,
  };
  if (request.headers.get("content-type")) {
    headers["Content-Type"] = request.headers.get("content-type")!;
  }

  let body: BodyInit | null = null;
  if (!["GET", "HEAD", "DELETE"].includes(request.method)) {
    body = await request.text();
  }

  const upstream = await fetch(url, {
    method: request.method,
    headers,
    body,
  }).catch(() => null);

  if (!upstream) {
    return Response.json({ error: "service_unavailable" }, { status: 503 });
  }

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

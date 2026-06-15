// Server-seitiger Proxy für den Citation-Endpunkt (§3.7).
// FASTAPI_URL liegt nur im Server-Bundle — nie im Client.

import { type NextRequest, NextResponse } from "next/server";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(
  _req: NextRequest,
  context: RouteContext
): Promise<NextResponse> {
  const { id } = await context.params;

  let res: Response;
  try {
    res = await fetch(`${FASTAPI_URL}/api/v1/citation/${id}`, {
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: "citation_service_unavailable" },
      { status: 503 }
    );
  }

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

// Typsicherer Client für den Route-Handler-Proxy (nicht direkt für FastAPI).
// API-Keys und FastAPI-URL niemals im Client-Bundle (§3.7).

import type { ChatResponse, CitationResponse } from "@/types/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function sendMessage(
  message: string,
  sessionId: string | null
): Promise<ChatResponse> {
  const body: { message: string; session_id?: string } = { message };
  if (sessionId) body.session_id = sessionId;

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });

  if (!res.ok) {
    throw new ApiError(res.status, `Fehler ${res.status}`);
  }
  return res.json() as Promise<ChatResponse>;
}

export async function fetchCitation(cvId: string): Promise<CitationResponse> {
  const res = await fetch(`/api/citation/${cvId}`, {
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw new ApiError(res.status, `Quelle nicht abrufbar (${res.status})`);
  }
  return res.json() as Promise<CitationResponse>;
}

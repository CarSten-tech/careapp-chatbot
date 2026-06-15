// Setzt das Consent-Cookie (HttpOnly, SameSite=Lax) nach aktiver Nutzer-Zustimmung.
// Cookie ist HttpOnly damit XSS es nicht löschen kann; Middleware liest es server-seitig.

export async function POST(): Promise<Response> {
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie":
        "careapp_consent=true; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000",
    },
  });
}

// Zwei Gates:
// 1. Chat-Gate (§3.4): kein Chat ohne Einwilligung
// 2. Admin-Gate: kein /admin/* ohne Admin-Token-Cookie (außer /admin/login)

import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  // Admin-Bereich
  if (pathname.startsWith("/admin")) {
    if (pathname === "/admin/login") {
      return NextResponse.next();
    }
    const token = request.cookies.get("careapp_admin_token")?.value;
    if (!token) {
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = "/admin/login";
      loginUrl.searchParams.set("next", pathname);
      return NextResponse.redirect(loginUrl);
    }
    return NextResponse.next();
  }

  // Chat-Gate
  if (pathname.startsWith("/chat")) {
    const consent = request.cookies.get("careapp_consent")?.value;
    if (consent === "true") {
      return NextResponse.next();
    }
    const consentUrl = request.nextUrl.clone();
    consentUrl.pathname = "/consent";
    consentUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(consentUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/chat", "/chat/:path*", "/admin", "/admin/:path*"],
};

import { redirect } from "next/navigation";

// Startseite leitet zum Chat weiter — Middleware prüft Consent-Gate.
export default function Home() {
  redirect("/chat");
}

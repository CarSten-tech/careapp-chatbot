"use client";

import { useRouter } from "next/navigation";

interface Props {
  nextPath?: string;
}

export default function ConsentBanner({ nextPath = "/chat" }: Props) {
  const router = useRouter();

  async function handleConsent() {
    // Consent-Cookie über Route Handler setzen (HttpOnly — server-seitig)
    await fetch("/api/consent", { method: "POST", credentials: "same-origin" });
    router.replace(nextPath);
  }

  return (
    <div className="text-center space-y-4" role="dialog" aria-labelledby="consent-title">
      <p id="consent-title" className="text-gray-600 text-sm">
        Prototyp – Pflegeberatung (anonym, geprüfte Quellen)
      </p>
      <button
        type="button"
        onClick={handleConsent}
        className="px-6 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50"
      >
        Starten
      </button>
    </div>
  );
}

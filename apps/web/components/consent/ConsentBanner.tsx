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
    <div
      className="max-w-xl w-full bg-white rounded-2xl shadow-sm border border-gray-200 p-8 space-y-6"
      role="dialog"
      aria-labelledby="consent-title"
      aria-describedby="consent-desc"
    >
      <div className="space-y-2">
        <h1 id="consent-title" className="text-xl font-semibold text-gray-900">
          CareApp – Pflegeberatung
        </h1>
        <p id="consent-desc" className="text-sm text-gray-600 leading-relaxed">
          Dieser Chatbot beantwortet Fragen zu Pflege und sozialen Leistungen im
          Raum Kreis Neuss / Düsseldorf. Alle Antworten basieren ausschließlich
          auf redaktionell geprüften Inhalten — keine freien Modellantworten.
        </p>
      </div>

      <div className="space-y-3 text-sm text-gray-700">
        <div className="flex gap-2">
          <span className="text-green-600 font-bold flex-shrink-0">✓</span>
          <span>Jede Fachaussage ist mit einer geprüften Quelle belegt.</span>
        </div>
        <div className="flex gap-2">
          <span className="text-green-600 font-bold flex-shrink-0">✓</span>
          <span>Kein Diagnosesystem — kein Ersatz für individuelle Rechtsberatung.</span>
        </div>
        <div className="flex gap-2">
          <span className="text-green-600 font-bold flex-shrink-0">✓</span>
          <span>Gespräch wird nicht mit Ihrem Namen verknüpft (anonyme Session).</span>
        </div>
      </div>

      <div className="space-y-3">
        <button
          type="button"
          onClick={handleConsent}
          className="w-full rounded-xl bg-blue-600 text-white py-3 text-sm font-medium
                     hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                     transition-colors"
        >
          Verstanden — Beratung starten
        </button>
        <p className="text-xs text-gray-400 text-center">
          Mit dem Start stimmen Sie der Nutzung einer anonymen Sitzung zu.
        </p>
      </div>
    </div>
  );
}

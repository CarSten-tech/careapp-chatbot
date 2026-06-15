"use client";

// ⓘ-Button + Citation-Modal für factual_statement-Blöcke (§3.5 Quelltransparenz).
// Jede claim_version_id bekommt einen eigenen Button. Fetch beim Klick (lazy).

import { useState } from "react";
import { fetchCitation, ApiError } from "@/lib/api-client";
import type { CitationResponse } from "@/types/api";

interface Props {
  cvId: string;
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  law: "Gesetz",
  guideline: "Richtlinie",
  expert_text: "Fachtext",
  directory: "Verzeichnis",
};

const ROLE_LABELS: Record<string, string> = {
  carrying: "Hauptbeleg",
  supporting: "Ergänzend",
  contextual: "Kontext",
};

export default function CitationButton({ cvId }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<CitationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleOpen() {
    setOpen(true);
    if (data) return; // bereits geladen
    setLoading(true);
    setError(null);
    try {
      const res = await fetchCitation(cvId);
      setData(res);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Quelle konnte nicht geladen werden."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleClose() {
    setOpen(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="text-xs text-blue-400 hover:text-blue-600 cursor-pointer ml-0.5"
        aria-label="Quellinformation anzeigen"
        title="Quelle ansehen"
      >
        ⓘ
      </button>

      {open && (
        // Backdrop
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={handleClose}
          aria-hidden="true"
        >
          {/* Modal */}
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="citation-title"
            className="relative bg-white rounded-xl shadow-xl max-w-lg w-full p-5 space-y-4 max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={handleClose}
              className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 text-lg leading-none"
              aria-label="Schließen"
            >
              ✕
            </button>

            <h2 id="citation-title" className="text-sm font-semibold text-gray-800 pr-6">
              Geprüfte Quelle
            </h2>

            {loading && (
              <p className="text-sm text-gray-500 animate-pulse">Wird geladen…</p>
            )}

            {error && (
              <p className="text-sm text-red-600">{error}</p>
            )}

            {data && (
              <div className="space-y-3">
                {/* Fachaussage */}
                <div className="rounded-lg bg-blue-50 border border-blue-200 p-3">
                  <p className="text-xs text-blue-600 font-medium mb-1">Fachaussage</p>
                  <p className="text-sm text-gray-800">{data.statement_text}</p>
                </div>

                {/* Belegstellen */}
                {data.evidences.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                      Belegstellen ({data.evidences.length})
                    </p>
                    {data.evidences.map((ev, i) => (
                      <div
                        key={i}
                        className="rounded border border-gray-200 p-3 space-y-1"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">
                            {SOURCE_TYPE_LABELS[ev.source_type] ?? ev.source_type}
                          </span>
                          <span className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">
                            {ROLE_LABELS[ev.role] ?? ev.role}
                          </span>
                        </div>
                        <p className="text-xs font-medium text-gray-700">
                          {ev.publisher} · {ev.canonical_ref}
                        </p>
                        <p className="text-xs text-gray-500">{ev.edition_label}</p>
                        <blockquote className="text-xs text-gray-600 italic border-l-2 border-blue-300 pl-2 mt-1">
                          {ev.quote}
                        </blockquote>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400">
                    Keine Belegstellen hinterlegt.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

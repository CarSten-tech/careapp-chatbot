"use client";

import { useEffect, useState } from "react";

interface SourceVersion {
  id: string;
  edition_label: string;
  imported_at: string;
  passages_count: number;
}

interface SourceDocument {
  id: string;
  type: string;
  publisher: string;
  canonical_ref: string;
  created_at: string;
  versions: SourceVersion[];
}

interface PassageIn {
  anchor: { section: string };
  text: string;
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  law: "Gesetz",
  guideline: "Leitlinie",
  expert_text: "Fachliteratur",
  directory: "Verzeichnis",
};

const SOURCE_TYPE_OPTIONS = ["law", "guideline", "expert_text", "directory"];

export default function SourcesPage() {
  const [docs, setDocs] = useState<SourceDocument[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [showForm, setShowForm] = useState(false);

  // Form state
  const [type, setType] = useState("law");
  const [publisher, setPublisher] = useState("");
  const [canonicalRef, setCanonicalRef] = useState("");
  const [editionLabel, setEditionLabel] = useState("");
  const [passages, setPassages] = useState<PassageIn[]>([
    { anchor: { section: "" }, text: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadDocs() {
    setLoadingList(true);
    try {
      const res = await fetch("/api/admin/sources");
      if (res.ok) setDocs(await res.json());
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    void loadDocs();
  }, []);

  function addPassage() {
    setPassages((p) => [...p, { anchor: { section: "" }, text: "" }]);
  }

  function removePassage(i: number) {
    setPassages((p) => p.filter((_, idx) => idx !== i));
  }

  function updatePassage(i: number, field: "section" | "text", val: string) {
    setPassages((p) =>
      p.map((row, idx) =>
        idx === i
          ? field === "text"
            ? { ...row, text: val }
            : { ...row, anchor: { section: val } }
          : row
      )
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const res = await fetch("/api/admin/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type,
          publisher,
          canonical_ref: canonicalRef,
          edition_label: editionLabel,
          passages: passages.map((p) => ({ anchor: p.anchor, text: p.text })),
        }),
      });
      if (res.ok) {
        setShowForm(false);
        setPublisher("");
        setCanonicalRef("");
        setEditionLabel("");
        setPassages([{ anchor: { section: "" }, text: "" }]);
        await loadDocs();
      } else {
        const err = await res.json().catch(() => ({ detail: "Fehler" }));
        setError(err.detail ?? "Fehler beim Speichern");
      }
    } catch {
      setError("Verbindungsfehler");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-slate-800">Quelldokumente</h1>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="bg-slate-800 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-slate-700"
        >
          {showForm ? "Abbrechen" : "+ Neues Dokument"}
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 mb-6">
          <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wide mb-4">
            Neues Quelldokument anlegen
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-700 mb-1 font-medium">Typ</label>
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
                >
                  {SOURCE_TYPE_OPTIONS.map((t) => (
                    <option key={t} value={t}>
                      {SOURCE_TYPE_LABELS[t] ?? t}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-slate-700 mb-1 font-medium">
                  Herausgeber <span className="text-red-500">*</span>
                </label>
                <input
                  value={publisher}
                  onChange={(e) => setPublisher(e.target.value)}
                  required
                  placeholder="z. B. Bundesministerium für Gesundheit"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-700 mb-1 font-medium">
                  Referenz (canonical_ref) <span className="text-red-500">*</span>
                </label>
                <input
                  value={canonicalRef}
                  onChange={(e) => setCanonicalRef(e.target.value)}
                  required
                  placeholder="z. B. SGB-XI-2024"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-700 mb-1 font-medium">
                  Edition / Fassung <span className="text-red-500">*</span>
                </label>
                <input
                  value={editionLabel}
                  onChange={(e) => setEditionLabel(e.target.value)}
                  required
                  placeholder="z. B. i.d.F. 23.10.2024"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-700 mb-2 font-medium">
                Passagen (Textabschnitte)
              </label>
              <div className="space-y-3">
                {passages.map((p, i) => (
                  <div key={i} className="border border-slate-200 rounded-lg p-3 space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        value={p.anchor.section}
                        onChange={(e) => updatePassage(i, "section", e.target.value)}
                        placeholder="Abschnitt (z. B. §43 Abs. 1)"
                        className="flex-1 border border-slate-300 rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-slate-500"
                      />
                      {passages.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removePassage(i)}
                          className="text-red-400 hover:text-red-600 text-xs"
                        >
                          ✕ Entfernen
                        </button>
                      )}
                    </div>
                    <textarea
                      value={p.text}
                      onChange={(e) => updatePassage(i, "text", e.target.value)}
                      rows={3}
                      required
                      placeholder="Originaltext der Passage …"
                      className="w-full border border-slate-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500 resize-none"
                    />
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={addPassage}
                className="mt-2 text-sm text-blue-600 hover:underline"
              >
                + Passage hinzufügen
              </button>
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={saving}
                className="bg-slate-800 text-white rounded-lg px-6 py-2 text-sm font-medium hover:bg-slate-700 disabled:opacity-50"
              >
                {saving ? "Wird gespeichert …" : "Dokument anlegen"}
              </button>
            </div>
          </form>
        </div>
      )}

      {loadingList ? (
        <p className="text-slate-400 text-sm">Wird geladen …</p>
      ) : docs.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center text-slate-400 text-sm">
          Noch keine Quelldokumente vorhanden.
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Dokument
                </th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-24">
                  Typ
                </th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">
                  Edition
                </th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-24">
                  Passagen
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((doc) => {
                const latestVersion = doc.versions[0];
                return (
                  <tr key={doc.id}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{doc.publisher}</p>
                      <p className="text-xs font-mono text-slate-400">{doc.canonical_ref}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">
                      {SOURCE_TYPE_LABELS[doc.type] ?? doc.type}
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-xs">
                      {latestVersion?.edition_label ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-700 font-medium">
                      {latestVersion?.passages_count ?? 0}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

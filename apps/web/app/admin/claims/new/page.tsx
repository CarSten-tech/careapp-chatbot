"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface ScopeRow {
  dimension: string;
  value: string;
}

const DIMENSION_OPTIONS = ["topic", "region", "target_group"];
const REGION_BINDING_OPTIONS = ["region_independent", "region_specific"];

export default function NewClaimPage() {
  const router = useRouter();
  const [statementText, setStatementText] = useState("");
  const [topicScope, setTopicScope] = useState("stationaere_pflege");
  const [regionBinding, setRegionBinding] = useState("region_independent");
  const [scopes, setScopes] = useState<ScopeRow[]>([
    { dimension: "topic", value: "stationaere_pflege" },
    { dimension: "region", value: "DE_FEDERAL" },
    { dimension: "target_group", value: "relative" },
    { dimension: "target_group", value: "patient" },
  ]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function addScope() {
    setScopes((s) => [...s, { dimension: "topic", value: "" }]);
  }

  function removeScope(i: number) {
    setScopes((s) => s.filter((_, idx) => idx !== i));
  }

  function updateScope(i: number, field: "dimension" | "value", val: string) {
    setScopes((s) => s.map((row, idx) => (idx === i ? { ...row, [field]: val } : row)));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const res = await fetch("/api/admin/claims", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          statement_text: statementText,
          topic_scope: topicScope,
          region_binding: regionBinding,
          scope_assignments: scopes.map((s) => ({
            dimension: s.dimension,
            value: s.value,
            applies: true,
          })),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        router.push(`/admin/claims/${data.id}`);
      } else {
        const err = await res.json().catch(() => ({ detail: "Unbekannter Fehler" }));
        setError(err.detail ?? "Fehler beim Speichern");
      }
    } catch {
      setError("Verbindungsfehler");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => router.back()}
          className="text-slate-400 hover:text-slate-600 text-sm"
        >
          ← Zurück
        </button>
        <h1 className="text-2xl font-semibold text-slate-800">Neue Fachaussage</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Inhalt</h2>

          <div>
            <label className="block text-sm text-slate-700 mb-1 font-medium">
              Fachaussage <span className="text-red-500">*</span>
            </label>
            <textarea
              value={statementText}
              onChange={(e) => setStatementText(e.target.value)}
              rows={4}
              required
              minLength={10}
              placeholder="Exakte, belegbare Fachaussage eingeben …"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500 resize-none"
            />
            <p className="text-xs text-slate-400 mt-1">
              Nur exakte, durch eine Quelle belegbare Aussagen. Keine Interpretationen.
            </p>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 space-y-4">
          <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">Scope</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-700 mb-1 font-medium">Thema (topic_scope)</label>
              <input
                value={topicScope}
                onChange={(e) => setTopicScope(e.target.value)}
                required
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500 font-mono"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-700 mb-1 font-medium">Region</label>
              <select
                value={regionBinding}
                onChange={(e) => setRegionBinding(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              >
                {REGION_BINDING_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-slate-700 mb-2 font-medium">
              Scope-Zuweisungen
            </label>
            <div className="space-y-2">
              {scopes.map((row, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <select
                    value={row.dimension}
                    onChange={(e) => updateScope(i, "dimension", e.target.value)}
                    className="border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500 w-36"
                  >
                    {DIMENSION_OPTIONS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                  <input
                    value={row.value}
                    onChange={(e) => updateScope(i, "value", e.target.value)}
                    placeholder="Wert"
                    className="flex-1 border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500 font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => removeScope(i)}
                    className="text-red-400 hover:text-red-600 text-sm px-1"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addScope}
              className="mt-2 text-sm text-blue-600 hover:underline"
            >
              + Zuweisung hinzufügen
            </button>
          </div>
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
            {saving ? "Wird gespeichert …" : "Als Entwurf speichern"}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="border border-slate-300 rounded-lg px-6 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Abbrechen
          </button>
        </div>
      </form>
    </div>
  );
}

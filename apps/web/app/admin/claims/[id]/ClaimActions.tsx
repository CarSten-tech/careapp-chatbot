"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

interface Approval {
  id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  at: string;
  four_eyes_of: string | null;
}

interface Props {
  cvId: string;
  currentStatus: string;
  approvals: Approval[];
}

// Welche Aktionen sind in welchem Status erlaubt?
const TRANSITION_BUTTONS: Record<string, { label: string; target: string; color: string }[]> = {
  draft: [{ label: "Zur Prüfung einreichen", target: "in_review", color: "slate" }],
  in_review: [
    { label: "Zurück zu Entwurf", target: "draft", color: "slate-outline" },
    { label: "Zurückziehen", target: "withdrawn", color: "red-outline" },
  ],
  approved: [{ label: "Zurückziehen", target: "withdrawn", color: "red-outline" }],
  published: [{ label: "Zurückziehen", target: "withdrawn", color: "red-outline" }],
};

// In welchem Status kann eine Freigabe hinzugefügt werden?
const CAN_APPROVE: Record<string, { action: string; role: string; label: string }[]> = {
  in_review: [{ action: "approve", role: "editor", label: "Erste Freigabe (Redakteur)" }],
  approved: [{ action: "publish", role: "chief_editor", label: "Zweite Freigabe + Veröffentlichen (Chefredakteur)" }],
};

type BtnColor = "slate" | "slate-outline" | "red-outline" | "green";

function btnClass(color: BtnColor): string {
  const map: Record<BtnColor, string> = {
    slate: "bg-slate-800 text-white hover:bg-slate-700",
    "slate-outline": "border border-slate-300 text-slate-600 hover:bg-slate-50",
    "red-outline": "border border-red-300 text-red-600 hover:bg-red-50",
    green: "bg-green-700 text-white hover:bg-green-600",
  };
  return `rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50 ${map[color]}`;
}

export function ClaimActions({ cvId, currentStatus, approvals }: Props) {
  const router = useRouter();
  const [actorId, setActorId] = useState("");
  const [fourEyesOf, setFourEyesOf] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const transitions = TRANSITION_BUTTONS[currentStatus] ?? [];
  const approvalOptions = CAN_APPROVE[currentStatus] ?? [];

  // Ersten Genehmiger-ID vorausfüllen für Vier-Augen
  const firstApprovalActorId = approvals.find((a) => a.action === "approve")?.actor_id ?? "";

  async function doTransition(target: string) {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/claims/${cvId}/transition`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_status: target }),
      });
      if (res.ok) {
        router.refresh();
      } else {
        const err = await res.json().catch(() => ({ detail: "Fehler" }));
        setError(err.detail ?? "Fehler");
      }
    } catch {
      setError("Verbindungsfehler");
    } finally {
      setLoading(false);
    }
  }

  async function doApprove(action: string, role: string) {
    if (!actorId.trim()) {
      setError("Bitte Name / ID eingeben.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const body: {
        actor_id: string;
        actor_role: string;
        action: string;
        four_eyes_of?: string;
      } = {
        actor_id: actorId.trim(),
        actor_role: role,
        action,
      };
      if (action === "publish" && (fourEyesOf.trim() || firstApprovalActorId)) {
        body.four_eyes_of = fourEyesOf.trim() || firstApprovalActorId;
      }
      const res = await fetch(`/api/admin/claims/${cvId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setActorId("");
        setFourEyesOf("");
        router.refresh();
      } else {
        const err = await res.json().catch(() => ({ detail: "Fehler" }));
        setError(err.detail ?? "Fehler");
      }
    } catch {
      setError("Verbindungsfehler");
    } finally {
      setLoading(false);
    }
  }

  if (transitions.length === 0 && approvalOptions.length === 0) {
    return (
      <p className="text-sm text-slate-400">Keine Aktionen für diesen Status verfügbar.</p>
    );
  }

  return (
    <div className="space-y-4">
      {approvalOptions.length > 0 && (
        <div className="space-y-3 border border-slate-200 rounded-lg p-4 bg-slate-50">
          <div>
            <label className="block text-xs text-slate-600 mb-1 font-medium">Ihr Name / Kennung</label>
            <input
              value={actorId}
              onChange={(e) => setActorId(e.target.value)}
              placeholder="z. B. maria.mueller"
              className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
            />
          </div>

          {currentStatus === "approved" && (
            <div>
              <label className="block text-xs text-slate-600 mb-1 font-medium">
                Erste Freigabe von (Vier-Augen)
              </label>
              <input
                value={fourEyesOf || firstApprovalActorId}
                onChange={(e) => setFourEyesOf(e.target.value)}
                placeholder={firstApprovalActorId || "Kennung der ersten Person"}
                className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {approvalOptions.map((opt) => (
              <button
                key={opt.action}
                onClick={() => doApprove(opt.action, opt.role)}
                disabled={loading}
                className={btnClass("green")}
              >
                ✓ {opt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {transitions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {transitions.map((t) => (
            <button
              key={t.target}
              onClick={() => doTransition(t.target)}
              disabled={loading}
              className={btnClass(t.color as BtnColor)}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

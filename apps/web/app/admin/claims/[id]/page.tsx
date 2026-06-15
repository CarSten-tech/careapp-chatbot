import Link from "next/link";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { ClaimActions } from "./ClaimActions";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

interface ScopeAssignment {
  id: string;
  dimension: string;
  value: string;
  applies: boolean;
}

interface Evidence {
  id: string;
  source_passage_id: string;
  role: string;
  quote: string;
}

interface Approval {
  id: string;
  actor_id: string;
  actor_role: string;
  action: string;
  at: string;
  four_eyes_of: string | null;
}

interface ClaimDetail {
  id: string;
  claim_id: string;
  statement_text: string;
  status: string;
  topic_scope: string;
  region_binding: string;
  effective_from: string | null;
  published_at: string | null;
  scope_assignments: ScopeAssignment[];
  evidences: Evidence[];
  approvals: Approval[];
}

async function fetchClaim(token: string, id: string): Promise<ClaimDetail | null> {
  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/admin/claims/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return res.json() as Promise<ClaimDetail>;
  } catch {
    return null;
  }
}

const STATUS_LABELS: Record<string, string> = {
  draft: "Entwurf",
  in_review: "In Prüfung",
  approved: "Freigegeben",
  published: "Veröffentlicht",
  superseded: "Abgelöst",
  withdrawn: "Zurückgezogen",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  in_review: "bg-yellow-100 text-yellow-800",
  approved: "bg-blue-100 text-blue-800",
  published: "bg-green-100 text-green-800",
  superseded: "bg-orange-100 text-orange-800",
  withdrawn: "bg-red-100 text-red-800",
};

const ACTOR_ROLE_LABELS: Record<string, string> = {
  editor: "Redakteur",
  chief_editor: "Chefredakteur",
};

const ACTION_LABELS: Record<string, string> = {
  approve: "Freigegeben",
  publish: "Veröffentlicht",
  reject: "Abgelehnt",
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function ClaimDetailPage({ params }: PageProps) {
  const { id } = await params;
  const cookieStore = await cookies();
  const token = cookieStore.get("careapp_admin_token")?.value ?? "";
  const cv = await fetchClaim(token, id);

  if (!cv) notFound();

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/admin/claims" className="text-slate-400 hover:text-slate-600 text-sm">
          ← Fachaussagen
        </Link>
        <span
          className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[cv.status] ?? "bg-slate-100 text-slate-700"}`}
        >
          {STATUS_LABELS[cv.status] ?? cv.status}
        </span>
      </div>

      <div className="space-y-6">
        {/* Aussage */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Fachaussage
          </h2>
          <p className="text-slate-800 leading-relaxed">{cv.statement_text}</p>
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-400">
            <span className="font-mono">topic: {cv.topic_scope}</span>
            <span>·</span>
            <span className="font-mono">region: {cv.region_binding}</span>
            <span>·</span>
            <span className="font-mono">ID: {cv.id}</span>
          </div>
        </div>

        {/* Scope */}
        {cv.scope_assignments.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Scope-Zuweisungen
            </h2>
            <div className="space-y-1">
              {cv.scope_assignments.map((sa) => (
                <div key={sa.id} className="flex items-center gap-2 text-sm">
                  <span className="w-28 font-mono text-slate-500 text-xs">{sa.dimension}</span>
                  <span className="font-mono text-slate-800">{sa.value}</span>
                  {!sa.applies && (
                    <span className="text-xs text-red-500">(ausgeschlossen)</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Belege */}
        {cv.evidences.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
              Quellenbelege
            </h2>
            <div className="space-y-3">
              {cv.evidences.map((e) => (
                <div key={e.id} className="border-l-4 border-blue-200 pl-4">
                  <p className="text-xs text-slate-400 mb-1 font-mono">{e.role} · Passage {e.source_passage_id}</p>
                  <blockquote className="text-sm text-slate-700 italic">&ldquo;{e.quote}&rdquo;</blockquote>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Freigabe-Workflow */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">
            Vier-Augen-Freigabe
          </h2>

          {cv.approvals.length > 0 && (
            <div className="mb-4 space-y-2">
              {cv.approvals.map((a) => (
                <div
                  key={a.id}
                  className="flex items-center justify-between text-sm bg-slate-50 rounded-lg px-3 py-2"
                >
                  <div>
                    <span className="font-medium text-slate-800">{a.actor_id}</span>
                    <span className="text-slate-400 ml-2 text-xs">
                      ({ACTOR_ROLE_LABELS[a.actor_role] ?? a.actor_role})
                    </span>
                    {a.four_eyes_of && (
                      <span className="text-slate-400 ml-2 text-xs">
                        Zweite Freigabe für: {a.four_eyes_of}
                      </span>
                    )}
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-medium text-green-700">
                      {ACTION_LABELS[a.action] ?? a.action}
                    </span>
                    <p className="text-xs text-slate-400">
                      {new Date(a.at).toLocaleString("de-DE")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {cv.approvals.length === 0 && (
            <p className="text-sm text-slate-400 mb-4">Noch keine Freigaben.</p>
          )}

          {/* Interaktive Aktionen (Client Component) */}
          <ClaimActions cvId={cv.id} currentStatus={cv.status} approvals={cv.approvals} />
        </div>
      </div>
    </div>
  );
}

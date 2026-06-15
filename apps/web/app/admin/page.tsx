import Link from "next/link";
import { cookies } from "next/headers";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

interface Stats {
  claims_total: number;
  claims_by_status: Record<string, number>;
  sources_total: number;
  passages_total: number;
}

async function fetchStats(token: string): Promise<Stats | null> {
  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/admin/stats`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json() as Promise<Stats>;
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

export default async function AdminDashboard() {
  const cookieStore = await cookies();
  const token = cookieStore.get("careapp_admin_token")?.value ?? "";
  const stats = await fetchStats(token);

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-semibold text-slate-800">Übersicht</h1>
      </div>

      {!stats ? (
        <p className="text-slate-500 text-sm">Statistiken nicht verfügbar (FastAPI erreichbar?)</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <StatCard label="Fachaussagen gesamt" value={stats.claims_total} href="/admin/claims" />
          <StatCard label="Quelldokumente" value={stats.sources_total} href="/admin/sources" />
          <StatCard label="Passagen" value={stats.passages_total} href="/admin/sources" />
        </div>
      )}

      {stats && Object.keys(stats.claims_by_status).length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
          <h2 className="text-sm font-semibold text-slate-600 uppercase tracking-wide mb-4">
            Fachaussagen nach Status
          </h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(stats.claims_by_status).map(([status, count]) => (
              <Link
                key={status}
                href={`/admin/claims?status=${status}`}
                className={`px-3 py-1.5 rounded-full text-sm font-medium ${STATUS_COLORS[status] ?? "bg-slate-100 text-slate-700"}`}
              >
                {STATUS_LABELS[status] ?? status}: {count}
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4">
        <ActionCard
          title="Neue Fachaussage"
          description="CV anlegen, Scope vergeben, Quellenbeleg hinzufügen"
          href="/admin/claims/new"
          cta="Anlegen"
        />
        <ActionCard
          title="Quelldokument importieren"
          description="Gesetz oder Leitlinie mit Passagen anlegen"
          href="/admin/sources"
          cta="Zur Quellverwaltung"
        />
      </div>
    </div>
  );
}

function StatCard({ label, value, href }: { label: string; value: number; href: string }) {
  return (
    <Link
      href={href}
      className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 hover:shadow-md transition-shadow"
    >
      <p className="text-3xl font-bold text-slate-800">{value}</p>
      <p className="text-sm text-slate-500 mt-1">{label}</p>
    </Link>
  );
}

function ActionCard({
  title,
  description,
  href,
  cta,
}: {
  title: string;
  description: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6">
      <h3 className="font-semibold text-slate-800 mb-1">{title}</h3>
      <p className="text-sm text-slate-500 mb-4">{description}</p>
      <Link
        href={href}
        className="inline-block bg-slate-800 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-slate-700"
      >
        {cta}
      </Link>
    </div>
  );
}

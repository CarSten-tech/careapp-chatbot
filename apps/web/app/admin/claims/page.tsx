import Link from "next/link";
import { cookies } from "next/headers";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

interface ClaimItem {
  id: string;
  claim_id: string;
  statement_text: string;
  status: string;
  topic_scope: string;
  region_binding: string;
  approvals_count: number;
  created_at: string;
}

async function fetchClaims(token: string, status?: string, topic?: string): Promise<ClaimItem[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (topic) params.set("topic", topic);
  try {
    const res = await fetch(`${FASTAPI_URL}/api/v1/admin/claims?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return [];
    return res.json() as Promise<ClaimItem[]>;
  } catch {
    return [];
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

interface PageProps {
  searchParams: Promise<{ status?: string; topic?: string }>;
}

export default async function ClaimsListPage({ searchParams }: PageProps) {
  const { status, topic } = await searchParams;
  const cookieStore = await cookies();
  const token = cookieStore.get("careapp_admin_token")?.value ?? "";
  const claims = await fetchClaims(token, status, topic);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-slate-800">Fachaussagen</h1>
        <Link
          href="/admin/claims/new"
          className="bg-slate-800 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-slate-700"
        >
          + Neue Fachaussage
        </Link>
      </div>

      <div className="flex gap-2 mb-6 flex-wrap">
        {["", "draft", "in_review", "approved", "published", "withdrawn"].map((s) => (
          <Link
            key={s || "all"}
            href={s ? `/admin/claims?status=${s}` : "/admin/claims"}
            className={`px-3 py-1 rounded-full text-xs font-medium border ${
              (status ?? "") === s
                ? "bg-slate-800 text-white border-slate-800"
                : "bg-white text-slate-600 border-slate-300 hover:border-slate-500"
            }`}
          >
            {s ? (STATUS_LABELS[s] ?? s) : "Alle"}
          </Link>
        ))}
      </div>

      {claims.length === 0 ? (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-12 text-center text-slate-400 text-sm">
          Keine Fachaussagen gefunden.
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">
                  Aussage
                </th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">
                  Thema
                </th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-36">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-20">
                  Freig.
                </th>
                <th className="w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {claims.map((cv) => (
                <tr key={cv.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-800">
                    <p className="line-clamp-2 max-w-md">{cv.statement_text}</p>
                  </td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{cv.topic_scope}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[cv.status] ?? "bg-slate-100 text-slate-700"}`}
                    >
                      {STATUS_LABELS[cv.status] ?? cv.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-center">{cv.approvals_count}/2</td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/admin/claims/${cv.id}`}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      Öffnen →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

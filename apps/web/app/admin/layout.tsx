import type { ReactNode } from "react";
import Link from "next/link";

export const metadata = { title: "CareApp Admin" };

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="bg-slate-800 text-white px-6 py-3 flex items-center gap-8 text-sm">
        <span className="font-semibold text-slate-200 tracking-wide">CareApp Admin</span>
        <Link href="/admin" className="hover:text-white text-slate-300">
          Übersicht
        </Link>
        <Link href="/admin/claims" className="hover:text-white text-slate-300">
          Fachaussagen
        </Link>
        <Link href="/admin/sources" className="hover:text-white text-slate-300">
          Quellen
        </Link>
      </nav>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}

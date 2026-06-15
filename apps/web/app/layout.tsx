import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "CareApp – Pflegeberatung",
  description:
    "Seriöse Beratung zu Pflege und sozialen Leistungen im Raum Kreis Neuss / Düsseldorf. Alle Antworten auf Basis geprüfter Quellen.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className={`${geist.variable} h-full`}>
      <body className="h-full bg-gray-50 text-gray-900 antialiased">{children}</body>
    </html>
  );
}

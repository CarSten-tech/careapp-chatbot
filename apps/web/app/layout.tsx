import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pflegeberatung",
  description: "Prototyp – Chatbot Pflegeberatung",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de" className="h-full">
      <body className="h-full text-gray-900">{children}</body>
    </html>
  );
}

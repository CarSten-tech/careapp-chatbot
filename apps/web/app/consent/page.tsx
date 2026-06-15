import type { Metadata } from "next";
import ConsentBanner from "@/components/consent/ConsentBanner";

export const metadata: Metadata = {
  title: "Einwilligung – CareApp",
};

interface Props {
  searchParams: Promise<{ next?: string }>;
}

export default async function ConsentPage({ searchParams }: Props) {
  const { next } = await searchParams;
  const nextPath = next?.startsWith("/") ? next : "/chat";

  return (
    <main className="min-h-screen flex items-center justify-center p-4">
      <ConsentBanner nextPath={nextPath} />
    </main>
  );
}

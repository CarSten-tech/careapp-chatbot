import type { Metadata } from "next";
import { cookies } from "next/headers";
import ChatContainer from "@/components/chat/ChatContainer";

export const metadata: Metadata = {
  title: "Pflegeberatung – CareApp",
};

export default async function ChatPage() {
  // Session-ID server-seitig aus HttpOnly-Cookie lesen (§3.7)
  const cookieStore = await cookies();
  const sessionId = cookieStore.get("careapp_session_id")?.value ?? null;

  return (
    <main className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-gray-200 bg-white px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-sm font-bold">
            C
          </div>
          <div>
            <h1 className="text-sm font-semibold text-gray-900">CareApp Pflegeberatung</h1>
            <p className="text-xs text-gray-500">Kreis Neuss / Düsseldorf · Geprüfte Quellen</p>
          </div>
        </div>
      </header>

      {/* Chat */}
      <div className="flex-1 overflow-hidden max-w-3xl w-full mx-auto">
        <ChatContainer initialSessionId={sessionId} />
      </div>
    </main>
  );
}

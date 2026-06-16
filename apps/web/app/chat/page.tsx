import type { Metadata } from "next";
import { cookies } from "next/headers";
import ChatContainer from "@/components/chat/ChatContainer";

export const metadata: Metadata = {
  title: "Pflegeberatung",
};

export default async function ChatPage() {
  const cookieStore = await cookies();
  const sessionId = cookieStore.get("careapp_session_id")?.value ?? null;

  return (
    <main className="flex flex-col h-screen bg-white">
      <div className="flex-1 overflow-hidden max-w-2xl w-full mx-auto">
        <ChatContainer initialSessionId={sessionId} />
      </div>
    </main>
  );
}

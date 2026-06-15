// TypeScript-Typen für die CareApp Chatbot API (aus FastAPI OpenAPI-Spec abgeleitet).
// Manuell gepflegt bis openapi-typescript generiert wird.

export interface StructuredValue {
  kind: string;
  value: string;
  unit: string | null;
}

export interface OutputBlock {
  type: "empathy" | "factual_statement" | "clarifying_question" | "fallback";
  text: string;
  claim_version_ids: string[];
  structured_values: StructuredValue[];
}

export type Disposition =
  | "presented"
  | "no_verified_information"
  | "safe_scope_response"
  | "human_handoff"
  | "clarify"
  | "safety_notice";

export interface ChatResponse {
  session_id: string;
  disposition: Disposition;
  blocks: OutputBlock[];
  audit_ref: string | null;
  fallback_reason: string | null;
  turn: number;
}

export interface SessionStateResponse {
  session_id: string;
  turn: number;
  clarify_rounds_used: number;
  pathway_progress: Record<string, string>;
}

// Citation (Quellinformation)

export interface EvidenceOut {
  role: string;
  quote: string;
  source_type: string;
  publisher: string;
  canonical_ref: string;
  edition_label: string;
}

export interface CitationResponse {
  claim_version_id: string;
  statement_text: string;
  status: string;
  topic_scope: string;
  evidences: EvidenceOut[];
}

// Internes Message-Format für die Chat-UI
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;           // user: Eingabetext; assistant: nicht genutzt (blocks statt text)
  blocks?: OutputBlock[];    // assistant: gerenderte Blöcke
  disposition?: Disposition;
  turn?: number;
}

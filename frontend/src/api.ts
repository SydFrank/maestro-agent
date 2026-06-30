// Typed client for the gateway API. Mirrors the backend Pydantic schemas.

const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8080";

export interface Citation {
  document_id: string;
  chunk_id: string;
  source: string;
  score: number;
  snippet: string;
}

export interface AgentStep {
  kind: "plan" | "tool_call" | "tool_result" | "retrieve" | "final";
  name?: string;
  content: string;
  meta?: Record<string, unknown>;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface AgentResponse {
  answer: string;
  citations: Citation[];
  steps: AgentStep[];
  usage: TokenUsage;
  conversation_id: string;
}

export interface LoginResult {
  access_token: string;
  tenant_id: string;
  role: string;
}

async function request<T>(path: string, opts: RequestInit, token?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.message || `请求失败 (${res.status})`);
  }
  return body as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<LoginResult>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  chat: (message: string, conversationId: string | null, token: string) =>
    request<AgentResponse>(
      "/v1/chat",
      {
        method: "POST",
        body: JSON.stringify({ message, conversation_id: conversationId }),
      },
      token
    ),

  ingest: (source: string, title: string, content: string, token: string) =>
    request<{ document_id: string; chunks: number }>(
      "/v1/documents",
      { method: "POST", body: JSON.stringify({ source, title, content }) },
      token
    ),
};

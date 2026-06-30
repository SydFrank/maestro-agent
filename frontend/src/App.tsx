import { useState } from "react";
import { api, AgentResponse, AgentStep, Citation } from "./api";

interface Session {
  token: string;
  tenantId: string;
  role: string;
  username: string;
}

interface ChatTurn {
  role: "user" | "assistant" | "error";
  content: string;
  citations?: Citation[];
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  if (!session) return <Login onLogin={setSession} />;
  return <Chat session={session} onLogout={() => setSession(null)} />;
}

function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit() {
    setErr("");
    setLoading(true);
    try {
      const r = await api.login(username, password);
      onLogin({ token: r.access_token, tenantId: r.tenant_id, role: r.role, username });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login">
      <div className="card">
        <h2>企业级 AI Agent 平台</h2>
        {err && <div className="err">{err}</div>}
        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名" />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="密码"
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit} disabled={loading}>
          {loading ? "登录中…" : "登录"}
        </button>
        <div className="hint">
          演示账号：admin / admin123（管理员）· alice / alice123（成员）
        </div>
      </div>
    </div>
  );
}

function Chat({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [usage, setUsage] = useState<AgentResponse["usage"] | null>(null);
  const [busy, setBusy] = useState(false);

  async function send() {
    const message = input.trim();
    if (!message || busy) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", content: message }]);
    setBusy(true);
    try {
      const r = await api.chat(message, conversationId, session.token);
      setConversationId(r.conversation_id);
      setSteps(r.steps);
      setUsage(r.usage);
      setTurns((t) => [...t, { role: "assistant", content: r.answer, citations: r.citations }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "error", content: (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <div className="topbar">
        <h1>企业级 AI Agent 平台</h1>
        <div>
          <span className="badge">
            {session.username} · {session.tenantId} · {session.role}
          </span>{" "}
          <span className="badge" style={{ cursor: "pointer" }} onClick={onLogout}>
            退出
          </span>
        </div>
      </div>
      <div className="layout">
        <div className="chat-col">
          <div className="messages">
            {turns.length === 0 && (
              <div className="msg assistant">
                你好，我是企业知识库智能助手。先以 admin 上传文档，再来提问试试引用溯源。
              </div>
            )}
            {turns.map((t, i) => (
              <div key={i} className={`msg ${t.role}`}>
                {t.content}
                {t.citations && t.citations.length > 0 && (
                  <div className="citations">
                    {t.citations.map((c, j) => (
                      <div className="citation" key={j}>
                        <span className="score">相关度 {c.score}</span>
                        <span className="src">[来源{j + 1}] {c.source}</span>
                        <div>{c.snippet}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="msg assistant">思考中…</div>}
          </div>
          <div className="composer">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="输入你的问题…"
            />
            <button onClick={send} disabled={busy}>
              发送
            </button>
          </div>
        </div>
        <div className="trace-col">
          <h3>Agent 推理 Trace</h3>
          {steps.length === 0 && <div className="step"><div className="body">发送消息后展示规划 / 工具调用 / 护栏过程</div></div>}
          {steps.map((s, i) => (
            <div className="step" key={i}>
              <span className={`kind ${s.kind}`}>{s.kind}{s.name ? ` · ${s.name}` : ""}</span>
              <div className="body">{s.content}</div>
            </div>
          ))}
          {usage && (
            <div className="usage">
              token 用量：输入 {usage.input_tokens} · 输出 {usage.output_tokens}
              <br />
              成本：${usage.cost_usd}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

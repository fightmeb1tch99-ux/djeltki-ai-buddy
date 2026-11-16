const { useState, useEffect, useRef, useCallback } = React;

const TOKEN_KEY = "ai_buddy_token";
const getToken = () => localStorage.getItem(TOKEN_KEY);
const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Ошибка ${res.status}`);
  return data;
}

const api = {
  login: (u, p) => request("/api/login", { method: "POST", body: JSON.stringify({ username: u, password: p }) }),
  me: () => request("/api/me"),
  logout: () => request("/api/logout", { method: "POST" }),
  chat: (m) => request("/api/chat", { method: "POST", body: JSON.stringify({ message: m }) }),
  history: () => request("/api/chat/history"),
  confirmAction: (id) => request(`/api/actions/${id}/confirm`, { method: "POST" }),
  cancelAction: (id) => request(`/api/actions/${id}/cancel`, { method: "POST" }),
  stages: () => request("/api/stages"),
  setTask: (id, done) => request(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ done }) }),
  leaveList: () => request("/api/leave-requests"),
  accessList: () => request("/api/access"),
  mentorDigest: () => request("/api/mentor/digest"),
  answerDigest: (qid, answer) => request("/api/mentor/digest/answer", { method: "POST", body: JSON.stringify({ question_id: qid, answer, audience: "all" }) }),
  metrics: () => request("/api/metrics"),
  interns: () => request("/api/mentor/interns"),
  accessPending: () => request("/api/access/pending"),
  grantAccess: (id) => request(`/api/access/${id}/grant`, { method: "POST" }),
  decideLeave: (id, decision) => request(`/api/leave-requests/${id}/decision`, { method: "POST", body: JSON.stringify({ decision }) }),
};

const HINTS = [
  "Как оформить отгул?",
  "Оформи отгул с 20 по 22 ноября",
  "Запроси доступ к VPN",
  "Какие у меня доступы?",
  "Что мне делать дальше?",
  "Где взять пропуск в офис?",
];

function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("demo");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const demos = [
    { user: "intern1", label: "Анна · стажёр" },
    { user: "intern2", label: "Борис · стажёр" },
    { user: "mentor1", label: "Мария · наставник" },
  ];

  async function submit(e) {
    e?.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err) {
      setError(err.message || "Не удалось войти");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">AI</div>
          <h1>AI-buddy</h1>
        </div>
        <p className="subtitle">ИИ-наставник для стажёров · Hack&Change 2026</p>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={submit}>
          <div className="field">
            <label>Логин</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="intern1" autoFocus />
          </div>
          <div className="field">
            <label>Пароль</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading || !username}>
            {loading ? "Входим…" : "Войти"}
          </button>
        </form>
        <div className="demo-accounts">
          <p>Быстрый вход (пароль demo):</p>
          <div className="demo-chips">
            {demos.map((d) => (
              <button key={d.user} className="demo-chip" type="button" onClick={() => onLogin(d.user, "demo").catch((e) => setError(e.message))}>
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Layout({ user, page, onNavigate, onLogout, children }) {
  const internNav = [{ id: "chat", label: "Чат" }];
  const mentorNav = [
    { id: "digest", label: "Дайджест" },
    { id: "interns", label: "Стажёры" },
    { id: "metrics", label: "Метрики" },
    { id: "access", label: "Доступы" },
  ];
  const nav = user.role === "mentor" ? mentorNav : internNav;
  const titles = { chat: "Чат с AI-buddy", digest: "Дайджест вопросов", interns: "Стажёры", metrics: "Метрики пользы", access: "Заявки на доступ" };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">AI</div>
          <span>AI-buddy</span>
        </div>
        <nav className="nav">
          {nav.map((item) => (
            <button key={item.id} className={`nav-item ${page === item.id ? "active" : ""}`} onClick={() => onNavigate(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <div className="name">{user.full_name}</div>
          <div className="role">{user.role === "mentor" ? "Наставник" : "Стажёр"}</div>
          <button className="btn btn-ghost" style={{ marginTop: 8, width: "100%" }} onClick={onLogout}>Выйти</button>
        </div>
      </aside>
      <div className="main">
        <header className="main-header"><h2>{titles[page] || "AI-buddy"}</h2></header>
        <div className="main-content">{children}</div>
      </div>
    </div>
  );
}

function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [stages, setStages] = useState(null);
  const [leaves, setLeaves] = useState([]);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const load = useCallback(async () => {
    const [hist, st, lv] = await Promise.all([
      api.history(),
      api.stages().catch(() => null),
      api.leaveList().catch(() => ({ items: [] })),
    ]);
    setMessages(hist.items);
    if (st) setStages(st);
    setLeaves(lv.items);
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function send(msg) {
    const value = (msg ?? text).trim();
    if (!value || sending) return;
    setText("");
    setSending(true);
    try {
      const res = await api.chat(value);
      setMessages((prev) => [...prev, { id: Date.now(), role: "user", kind: "text", text: value }, res.message]);
      if (["proposal", "done", "info"].includes(res.status)) {
        const [st, lv] = await Promise.all([api.stages().catch(() => null), api.leaveList().catch(() => ({ items: [] }))]);
        if (st) setStages(st);
        setLeaves(lv.items);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user", kind: "text", text: value },
        { id: Date.now() + 1, role: "assistant", kind: "text", text: err.message || "Ошибка" },
      ]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  async function confirm(id) {
    const res = await api.confirmAction(id);
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id && res.proposal ? res.proposal : m));
      if (res.message) next.push(res.message);
      return next;
    });
    const [st, lv] = await Promise.all([api.stages().catch(() => null), api.leaveList().catch(() => ({ items: [] }))]);
    if (st) setStages(st);
    setLeaves(lv.items);
  }

  async function cancel(id) {
    const res = await api.cancelAction(id);
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id && res.proposal ? res.proposal : m));
      if (res.message) next.push(res.message);
      return next;
    });
  }

  async function toggleTask(taskId, done) {
    const st = await api.setTask(taskId, done);
    setStages(st);
  }

  function onKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="chat-layout">
      <div className="chat-panel">
        <div className="messages">
          {messages.length === 0 && (
            <div className="empty">
              <div className="empty-icon">💬</div>
              <div>Напиши вопрос или выбери подсказку ниже</div>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.role}`}>
              {m.kind === "proposal" && m.payload ? (
                <div className={`proposal ${m.payload.state || ""}`}>
                  <div className="proposal-title">{m.payload.title || "Действие"}</div>
                  <div className="proposal-lines">
                    {(m.payload.lines || []).map((line, i) => <div key={i}>{line}</div>)}
                  </div>
                  {m.payload.state === "pending" && (
                    <div className="proposal-actions">
                      <button className="btn btn-success" onClick={() => confirm(m.id)}>Подтвердить</button>
                      <button className="btn btn-secondary" onClick={() => cancel(m.id)}>Отмена</button>
                    </div>
                  )}
                  {m.payload.state === "done" && <div style={{ fontSize: 13, color: "var(--success)" }}>✓ Выполнено</div>}
                  {m.payload.state === "cancelled" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Отменено</div>}
                  {m.payload.state === "failed" && <div style={{ fontSize: 13, color: "var(--danger)" }}>{m.payload.error || "Ошибка"}</div>}
                </div>
              ) : (
                <div className={`bubble ${m.kind === "escalated" ? "escalated" : m.kind === "answer" ? "answer" : ""}`}>{m.text}</div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey} placeholder="Напиши вопрос или действие…" rows={1} disabled={sending} />
            <button className="btn btn-primary" onClick={() => send()} disabled={sending || !text.trim()}>{sending ? "…" : "Отправить"}</button>
          </div>
          <div className="hints">
            {HINTS.map((h) => (
              <button key={h} className="hint" onClick={() => send(h)} disabled={sending}>{h}</button>
            ))}
          </div>
        </div>
      </div>
      <div className="side-panel">
        {stages && (
          <>
            <h3>Адаптация</h3>
            <div className="progress-bar"><div style={{ width: `${stages.progress_percent}%` }} /></div>
            <div className="progress-label">{stages.progress_percent}% пройдено</div>
            {stages.stages.map((stage) => (
              <div key={stage.id} className="stage">
                <div className="stage-title">
                  {stage.title}
                  <span className={`stage-badge ${stage.status}`}>{stage.done_count}/{stage.total}</span>
                </div>
                {stage.tasks.map((task) => (
                  <div key={task.id} className={`task ${task.status === "done" ? "done" : ""}`}>
                    <div className={`task-check ${task.status} ${task.auto ? "auto" : ""}`} onClick={() => !task.auto && toggleTask(task.id, task.status !== "done")}>
                      {task.status === "done" ? "✓" : task.status === "in_progress" ? "…" : ""}
                    </div>
                    <span>{task.title}</span>
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
        {leaves.length > 0 && (
          <>
            <h3 style={{ marginTop: 24 }}>Отгулы</h3>
            {leaves.map((l) => (
              <div key={l.id} className="list-card" style={{ padding: "10px 12px", marginBottom: 8 }}>
                <div>
                  <div className="title">{l.external_id}</div>
                  <div className="sub">{l.start_date} → {l.end_date}</div>
                </div>
                <span className={`badge ${l.status}`}>{l.status}</span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function DigestView() {
  const [items, setItems] = useState([]);
  const [answers, setAnswers] = useState({});
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    api.mentorDigest().then((r) => { setItems(r.items); setLoading(false); });
  }, []);
  useEffect(() => { load(); }, [load]);

  async function submit(qid) {
    const answer = (answers[qid] || "").trim();
    if (!answer) return;
    await api.answerDigest(qid, answer);
    setAnswers((prev) => ({ ...prev, [qid]: "" }));
    load();
  }

  if (loading) return <div className="empty">Загрузка…</div>;
  if (items.length === 0) return <div className="empty"><div className="empty-icon">✨</div><div>Нет вопросов без ответа. Отличная работа!</div></div>;

  return (
    <div className="digest-list">
      {items.map((item) => (
        <div key={item.question_id} className="digest-card">
          <div className="q">{item.text}</div>
          <div className="digest-meta">
            <span>Спросили: {item.asked_count}</span>
            {item.interns.map((n) => <span key={n}>{n}</span>)}
          </div>
          <div className="digest-answer">
            <textarea placeholder="Напиши ответ — его получат все, кто спрашивал…" value={answers[item.question_id] || ""} onChange={(e) => setAnswers((prev) => ({ ...prev, [item.question_id]: e.target.value }))} />
            <button className="btn btn-primary" style={{ width: "auto", alignSelf: "flex-start" }} onClick={() => submit(item.question_id)} disabled={!(answers[item.question_id] || "").trim()}>
              Ответить один раз
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function InternsView() {
  const [items, setItems] = useState([]);
  useEffect(() => { api.interns().then((r) => setItems(r.items)); }, []);
  if (items.length === 0) return <div className="empty">Нет стажёров</div>;
  return (
    <div className="intern-list">
      {items.map((i) => (
        <div key={i.id} className="intern-card">
          <div className="info">
            <div className="name">{i.full_name}</div>
            <div className="next">{i.next_step ? (i.next_step.waiting ? `Ждёт: ${i.next_step.title}` : `Следующий шаг: ${i.next_step.title}`) : "Адаптация завершена"}</div>
          </div>
          <div className="pct">{i.progress_percent}%</div>
        </div>
      ))}
    </div>
  );
}

function MetricsView() {
  const [m, setM] = useState(null);
  useEffect(() => { api.metrics().then(setM); }, []);
  if (!m) return <div className="empty">Загрузка…</div>;
  const cards = [
    { label: "Всего вопросов", value: m.total_questions },
    { label: "Без наставника", value: m.answered_without_mentor, highlight: true },
    { label: "Ждут ответа", value: m.pending },
    { label: "Ответил наставник", value: m.answered_by_mentor },
    { label: "Автоответы", value: `${Math.round(m.auto_rate * 100)}%`, highlight: true },
    { label: "Повторно из KB", value: m.reused_mentor_answers },
    { label: "Минут сэкономлено", value: m.mentor_minutes_saved, highlight: true },
    { label: "Среднее время ответа", value: m.avg_minutes_to_mentor_answer != null ? `${m.avg_minutes_to_mentor_answer} мин` : "—" },
  ];
  return (
    <div className="metrics-grid">
      {cards.map((c) => (
        <div key={c.label} className={`metric-card ${c.highlight ? "highlight" : ""}`}>
          <div className="value">{c.value}</div>
          <div className="label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}

function AccessView() {
  const [pending, setPending] = useState([]);
  const [leaves, setLeaves] = useState([]);
  const load = useCallback(() => {
    Promise.all([api.accessPending(), api.leaveList()]).then(([a, l]) => {
      setPending(a.items);
      setLeaves(l.items.filter((x) => x.status === "submitted"));
    });
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <h3 style={{ marginBottom: 14, fontSize: 15 }}>Доступы</h3>
      {pending.length === 0 ? <div className="empty" style={{ padding: 24 }}>Нет заявок на доступ</div> : pending.map((p) => (
        <div key={p.id} className="list-card">
          <div><div className="title">{p.system}</div><div className="sub">{p.full_name}</div></div>
          <button className="btn btn-success" style={{ width: "auto", padding: "8px 14px" }} onClick={async () => { await api.grantAccess(p.id); load(); }}>Выдать</button>
        </div>
      ))}
      <h3 style={{ margin: "28px 0 14px", fontSize: 15 }}>Отгулы на согласовании</h3>
      {leaves.length === 0 ? <div className="empty" style={{ padding: 24 }}>Нет заявок</div> : leaves.map((l) => (
        <div key={l.id} className="list-card">
          <div>
            <div className="title">{l.external_id} · {l.full_name || ""}</div>
            <div className="sub">{l.start_date} → {l.end_date}{l.reason ? ` · ${l.reason}` : ""}</div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-success" style={{ width: "auto", padding: "8px 12px" }} onClick={async () => { await api.decideLeave(l.id, "approve"); load(); }}>Одобрить</button>
            <button className="btn btn-secondary" style={{ width: "auto", padding: "8px 12px" }} onClick={async () => { await api.decideLeave(l.id, "reject"); load(); }}>Отклонить</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function MentorPage({ page }) {
  if (page === "digest") return <DigestView />;
  if (page === "interns") return <InternsView />;
  if (page === "metrics") return <MetricsView />;
  if (page === "access") return <AccessView />;
  return null;
}

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState("chat");

  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    api.me().then((u) => { setUser(u); setPage(u.role === "mentor" ? "digest" : "chat"); }).catch(() => setToken(null)).finally(() => setLoading(false));
  }, []);

  const handleLogin = useCallback(async (username, password) => {
    const { token, user } = await api.login(username, password);
    setToken(token);
    setUser(user);
    setPage(user.role === "mentor" ? "digest" : "chat");
  }, []);

  const handleLogout = useCallback(async () => {
    try { await api.logout(); } catch {}
    setToken(null);
    setUser(null);
  }, []);

  if (loading) return <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", color: "#94a3b8" }}>Загрузка…</div>;
  if (!user) return <Login onLogin={handleLogin} />;

  return (
    <Layout user={user} page={page} onNavigate={setPage} onLogout={handleLogout}>
      {user.role === "intern" && page === "chat" && <ChatPage />}
      {user.role === "mentor" && <MentorPage page={page} />}
    </Layout>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);

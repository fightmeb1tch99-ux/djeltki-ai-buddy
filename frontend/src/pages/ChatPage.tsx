import React, { useEffect, useRef, useState, useCallback } from "react";
import { api, Message, StagesResponse, LeaveRequest } from "../api/client";

const HINTS = [
  "Как оформить отгул?",
  "Оформи отгул с 20 по 22 ноября",
  "Запроси доступ к VPN",
  "Какие у меня доступы?",
  "Что мне делать дальше?",
  "Где взять пропуск в офис?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [stages, setStages] = useState<StagesResponse | null>(null);
  const [leaves, setLeaves] = useState<LeaveRequest[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(msg?: string) {
    const value = (msg ?? text).trim();
    if (!value || sending) return;
    setText("");
    setSending(true);
    try {
      const res = await api.chat(value);
      setMessages((prev) => [...prev, { id: Date.now(), role: "user", kind: "text", text: value, created_at: "" }, res.message]);
      if (res.status === "proposal" || res.status === "done" || res.status === "info") {
        const [st, lv] = await Promise.all([api.stages().catch(() => null), api.leaveList().catch(() => ({ items: [] }))]);
        if (st) setStages(st);
        setLeaves(lv.items);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user", kind: "text", text: value, created_at: "" },
        { id: Date.now() + 1, role: "assistant", kind: "text", text: err.message || "Ошибка", created_at: "" },
      ]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  }

  async function confirm(id: number) {
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

  async function cancel(id: number) {
    const res = await api.cancelAction(id);
    setMessages((prev) => {
      const next = prev.map((m) => (m.id === id && res.proposal ? res.proposal : m));
      if (res.message) next.push(res.message);
      return next;
    });
  }

  async function toggleTask(taskId: number, done: boolean) {
    const st = await api.setTask(taskId, done);
    setStages(st);
  }

  function onKey(e: React.KeyboardEvent) {
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
                    {(m.payload.lines || []).map((line: string, i: number) => (
                      <div key={i}>{line}</div>
                    ))}
                  </div>
                  {m.payload.state === "pending" && (
                    <div className="proposal-actions">
                      <button className="btn btn-success" onClick={() => confirm(m.id)}>
                        Подтвердить
                      </button>
                      <button className="btn btn-secondary" onClick={() => cancel(m.id)}>
                        Отмена
                      </button>
                    </div>
                  )}
                  {m.payload.state === "done" && <div style={{ fontSize: 13, color: "var(--success)" }}>✓ Выполнено</div>}
                  {m.payload.state === "cancelled" && <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Отменено</div>}
                  {m.payload.state === "failed" && (
                    <div style={{ fontSize: 13, color: "var(--danger)" }}>{m.payload.error || "Ошибка"}</div>
                  )}
                </div>
              ) : (
                <div className={`bubble ${m.kind === "escalated" ? "escalated" : m.kind === "answer" ? "answer" : ""}`}>
                  {m.text}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-row">
            <textarea
              ref={inputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onKey}
              placeholder="Напиши вопрос или действие…"
              rows={1}
              disabled={sending}
            />
            <button className="btn btn-primary" onClick={() => send()} disabled={sending || !text.trim()}>
              {sending ? "…" : "Отправить"}
            </button>
          </div>
          <div className="hints">
            {HINTS.map((h) => (
              <button key={h} className="hint" onClick={() => send(h)} disabled={sending}>
                {h}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="side-panel">
        {stages && (
          <>
            <h3>Адаптация</h3>
            <div className="progress-bar">
              <div style={{ width: `${stages.progress_percent}%` }} />
            </div>
            <div className="progress-label">{stages.progress_percent}% пройдено</div>

            {stages.stages.map((stage) => (
              <div key={stage.id} className="stage">
                <div className="stage-title">
                  {stage.title}
                  <span className={`stage-badge ${stage.status}`}>
                    {stage.done_count}/{stage.total}
                  </span>
                </div>
                {stage.tasks.map((task) => (
                  <div key={task.id} className={`task ${task.status === "done" ? "done" : ""}`}>
                    <div
                      className={`task-check ${task.status} ${task.auto ? "auto" : ""}`}
                      onClick={() => !task.auto && toggleTask(task.id, task.status !== "done")}
                    >
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
                  <div className="sub">
                    {l.start_date} → {l.end_date}
                  </div>
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

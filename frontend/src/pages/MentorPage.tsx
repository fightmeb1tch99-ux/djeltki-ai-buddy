import React, { useEffect, useState, useCallback } from "react";
import {
  api,
  DigestItem,
  Metrics,
  InternProgress,
  PendingAccess,
  LeaveRequest,
} from "../api/client";

interface Props {
  page: string;
}

export default function MentorPage({ page }: Props) {
  if (page === "digest") return <DigestView />;
  if (page === "interns") return <InternsView />;
  if (page === "metrics") return <MetricsView />;
  if (page === "access") return <AccessView />;
  return null;
}

function DigestView() {
  const [items, setItems] = useState<DigestItem[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api.mentorDigest().then((r) => {
      setItems(r.items);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function submit(qid: number) {
    const answer = (answers[qid] || "").trim();
    if (!answer) return;
    await api.answerDigest(qid, answer);
    setAnswers((prev) => ({ ...prev, [qid]: "" }));
    load();
  }

  if (loading) return <div className="empty">Загрузка…</div>;
  if (items.length === 0) {
    return (
      <div className="empty">
        <div className="empty-icon">✨</div>
        <div>Нет вопросов без ответа. Отличная работа!</div>
      </div>
    );
  }

  return (
    <div className="digest-list">
      {items.map((item) => (
        <div key={item.question_id} className="digest-card">
          <div className="q">{item.text}</div>
          <div className="digest-meta">
            <span>Спросили: {item.asked_count}</span>
            {item.interns.map((n) => (
              <span key={n}>{n}</span>
            ))}
          </div>
          <div className="digest-answer">
            <textarea
              placeholder="Напиши ответ — его получат все, кто спрашивал…"
              value={answers[item.question_id] || ""}
              onChange={(e) => setAnswers((prev) => ({ ...prev, [item.question_id]: e.target.value }))}
            />
            <button
              className="btn btn-primary"
              style={{ width: "auto", alignSelf: "flex-start" }}
              onClick={() => submit(item.question_id)}
              disabled={!(answers[item.question_id] || "").trim()}
            >
              Ответить один раз
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function InternsView() {
  const [items, setItems] = useState<InternProgress[]>([]);

  useEffect(() => {
    api.interns().then((r) => setItems(r.items));
  }, []);

  if (items.length === 0) return <div className="empty">Нет стажёров</div>;

  return (
    <div className="intern-list">
      {items.map((i) => (
        <div key={i.id} className="intern-card">
          <div className="info">
            <div className="name">{i.full_name}</div>
            <div className="next">
              {i.next_step
                ? i.next_step.waiting
                  ? `Ждёт: ${i.next_step.title}`
                  : `Следующий шаг: ${i.next_step.title}`
                : "Адаптация завершена"}
            </div>
          </div>
          <div className="pct">{i.progress_percent}%</div>
        </div>
      ))}
    </div>
  );
}

function MetricsView() {
  const [m, setM] = useState<Metrics | null>(null);

  useEffect(() => {
    api.metrics().then(setM);
  }, []);

  if (!m) return <div className="empty">Загрузка…</div>;

  const cards = [
    { label: "Всего вопросов", value: m.total_questions },
    { label: "Без наставника", value: m.answered_without_mentor, highlight: true },
    { label: "Ждут ответа", value: m.pending },
    { label: "Ответил наставник", value: m.answered_by_mentor },
    { label: "Автоответы", value: `${Math.round(m.auto_rate * 100)}%`, highlight: true },
    { label: "Повторно из KB", value: m.reused_mentor_answers },
    { label: "Минут сэкономлено", value: m.mentor_minutes_saved, highlight: true },
    {
      label: "Среднее время ответа",
      value: m.avg_minutes_to_mentor_answer != null ? `${m.avg_minutes_to_mentor_answer} мин` : "—",
    },
  ];

  return (
    <div>
      <div className="metrics-grid">
        {cards.map((c) => (
          <div key={c.label} className={`metric-card ${c.highlight ? "highlight" : ""}`}>
            <div className="value">{c.value}</div>
            <div className="label">{c.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AccessView() {
  const [pending, setPending] = useState<PendingAccess[]>([]);
  const [leaves, setLeaves] = useState<LeaveRequest[]>([]);

  const load = useCallback(() => {
    Promise.all([api.accessPending(), api.leaveList()]).then(([a, l]) => {
      setPending(a.items);
      setLeaves(l.items.filter((x) => x.status === "submitted"));
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function grant(id: number) {
    await api.grantAccess(id);
    load();
  }

  async function decide(id: number, decision: "approve" | "reject") {
    await api.decideLeave(id, decision);
    load();
  }

  return (
    <div>
      <h3 style={{ marginBottom: 14, fontSize: 15 }}>Доступы</h3>
      {pending.length === 0 ? (
        <div className="empty" style={{ padding: 24 }}>
          Нет заявок на доступ
        </div>
      ) : (
        pending.map((p) => (
          <div key={p.id} className="list-card">
            <div>
              <div className="title">{p.system}</div>
              <div className="sub">{p.full_name}</div>
            </div>
            <button className="btn btn-success" style={{ width: "auto", padding: "8px 14px" }} onClick={() => grant(p.id)}>
              Выдать
            </button>
          </div>
        ))
      )}

      <h3 style={{ margin: "28px 0 14px", fontSize: 15 }}>Отгулы на согласовании</h3>
      {leaves.length === 0 ? (
        <div className="empty" style={{ padding: 24 }}>
          Нет заявок
        </div>
      ) : (
        leaves.map((l) => (
          <div key={l.id} className="list-card">
            <div>
              <div className="title">
                {l.external_id} · {l.full_name || ""}
              </div>
              <div className="sub">
                {l.start_date} → {l.end_date}
                {l.reason ? ` · ${l.reason}` : ""}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-success" style={{ width: "auto", padding: "8px 12px" }} onClick={() => decide(l.id, "approve")}>
                Одобрить
              </button>
              <button className="btn btn-secondary" style={{ width: "auto", padding: "8px 12px" }} onClick={() => decide(l.id, "reject")}>
                Отклонить
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

import React from "react";
import { User } from "../api/client";

interface Props {
  user: User;
  page: string;
  onNavigate: (p: string) => void;
  onLogout: () => void;
  children: React.ReactNode;
}

const ICONS: Record<string, React.ReactNode> = {
  chat: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  digest: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  interns: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  metrics: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  ),
  access: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  ),
};

export default function Layout({ user, page, onNavigate, onLogout, children }: Props) {
  const internNav = [{ id: "chat", label: "Чат" }];
  const mentorNav = [
    { id: "digest", label: "Дайджест" },
    { id: "interns", label: "Стажёры" },
    { id: "metrics", label: "Метрики" },
    { id: "access", label: "Доступы" },
  ];
  const nav = user.role === "mentor" ? mentorNav : internNav;

  const titles: Record<string, string> = {
    chat: "Чат с AI-buddy",
    digest: "Дайджест вопросов",
    interns: "Стажёры",
    metrics: "Метрики пользы",
    access: "Заявки на доступ",
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon">AI</div>
          <span>AI-buddy</span>
        </div>
        <nav className="nav">
          {nav.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? "active" : ""}`}
              onClick={() => onNavigate(item.id)}
            >
              {ICONS[item.id]}
              {item.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-user">
          <div className="name">{user.full_name}</div>
          <div className="role">{user.role === "mentor" ? "Наставник" : "Стажёр"}</div>
          <button className="btn btn-ghost" style={{ marginTop: 8, width: "100%" }} onClick={onLogout}>
            Выйти
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="main-header">
          <h2>{titles[page] || "AI-buddy"}</h2>
        </header>
        <div className="main-content">{children}</div>
      </div>
    </div>
  );
}

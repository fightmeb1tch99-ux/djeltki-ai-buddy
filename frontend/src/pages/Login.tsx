import React, { useState } from "react";

interface Props {
  onLogin: (username: string, password: string) => Promise<void>;
}

const DEMOS = [
  { user: "intern1", label: "Анна · стажёр" },
  { user: "intern2", label: "Борис · стажёр" },
  { user: "mentor1", label: "Мария · наставник" },
];

export default function Login({ onLogin }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("demo");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(username.trim(), password);
    } catch (err: any) {
      setError(err.message || "Не удалось войти");
    } finally {
      setLoading(false);
    }
  }

  function quick(user: string) {
    setUsername(user);
    setPassword("demo");
    setTimeout(() => {
      setUsername(user);
      onLogin(user, "demo").catch((err) => setError(err.message));
    }, 0);
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
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="intern1"
              autoFocus
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label>Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading || !username}>
            {loading ? "Входим…" : "Войти"}
          </button>
        </form>

        <div className="demo-accounts">
          <p>Быстрый вход (пароль demo):</p>
          <div className="demo-chips">
            {DEMOS.map((d) => (
              <button key={d.user} className="demo-chip" type="button" onClick={() => quick(d.user)}>
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

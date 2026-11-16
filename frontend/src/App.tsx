import React, { useEffect, useState, useCallback } from "react";
import { api, getToken, setToken, User } from "./api/client";
import Login from "./pages/Login";
import ChatPage from "./pages/ChatPage";
import MentorPage from "./pages/MentorPage";
import Layout from "./components/Layout";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState("chat");

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api.me()
      .then((u) => {
        setUser(u);
        setPage(u.role === "mentor" ? "digest" : "chat");
      })
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  const handleLogin = useCallback(async (username: string, password: string) => {
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

  if (loading) {
    return (
      <div style={{ display: "flex", height: "100%", alignItems: "center", justifyContent: "center", color: "#94a3b8" }}>
        Загрузка…
      </div>
    );
  }

  if (!user) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Layout user={user} page={page} onNavigate={setPage} onLogout={handleLogout}>
      {user.role === "intern" && page === "chat" && <ChatPage />}
      {user.role === "mentor" && <MentorPage page={page} />}
    </Layout>
  );
}

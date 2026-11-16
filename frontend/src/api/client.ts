const TOKEN_KEY = "ai_buddy_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Ошибка ${res.status}`);
  }
  return data as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  me: () => request<User>("/api/me"),

  logout: () => request("/api/logout", { method: "POST" }),

  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  history: () => request<{ items: Message[] }>("/api/chat/history"),

  confirmAction: (id: number) =>
    request<ActionResult>(`/api/actions/${id}/confirm`, { method: "POST" }),

  cancelAction: (id: number) =>
    request<ActionResult>(`/api/actions/${id}/cancel`, { method: "POST" }),

  stages: () => request<StagesResponse>("/api/stages"),

  setTask: (id: number, done: boolean) =>
    request<StagesResponse>(`/api/tasks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ done }),
    }),

  leaveList: () => request<{ items: LeaveRequest[] }>("/api/leave-requests"),

  accessList: () => request<{ items: AccessItem[]; available_systems: string[] }>("/api/access"),

  mentorDigest: () => request<{ items: DigestItem[] }>("/api/mentor/digest"),

  answerDigest: (question_id: number, answer: string, audience = "all") =>
    request<{ closed_questions: number }>("/api/mentor/digest/answer", {
      method: "POST",
      body: JSON.stringify({ question_id, answer, audience }),
    }),

  metrics: () => request<Metrics>("/api/metrics"),

  interns: () => request<{ items: InternProgress[] }>("/api/mentor/interns"),

  accessPending: () => request<{ items: PendingAccess[] }>("/api/access/pending"),

  grantAccess: (id: number) =>
    request(`/api/access/${id}/grant`, { method: "POST" }),

  decideLeave: (id: number, decision: "approve" | "reject") =>
    request(`/api/leave-requests/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
};

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: "intern" | "mentor";
}

export interface Message {
  id: number;
  role: "user" | "assistant";
  kind: string;
  text: string;
  payload?: any;
  created_at: string;
}

export interface ChatResponse {
  status: string;
  answer: string;
  message: Message;
  suggested_action?: string;
  source?: any;
  score?: number;
}

export interface ActionResult {
  state: string;
  proposal?: Message;
  message?: Message;
  result?: any;
  error?: string;
}

export interface StagesResponse {
  stages: Stage[];
  progress_percent: number;
  next_step: NextStep | null;
}

export interface Stage {
  id: number;
  title: string;
  description: string;
  status: string;
  done_count: number;
  total: number;
  tasks: Task[];
}

export interface Task {
  id: number;
  title: string;
  status: string;
  auto: boolean;
}

export interface NextStep {
  task_id: number;
  title: string;
  stage_title: string;
  waiting: boolean;
}

export interface LeaveRequest {
  id: number;
  external_id: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: string;
  full_name?: string;
}

export interface AccessItem {
  id: number;
  system: string;
  status: string;
}

export interface DigestItem {
  question_id: number;
  text: string;
  asked_count: number;
  interns: string[];
  first_asked: string;
}

export interface Metrics {
  total_questions: number;
  answered_without_mentor: number;
  pending: number;
  answered_by_mentor: number;
  auto_rate: number;
  reused_mentor_answers: number;
  mentor_minutes_saved: number;
  avg_minutes_to_mentor_answer: number | null;
  events: Record<string, number>;
}

export interface InternProgress {
  id: number;
  full_name: string;
  progress_percent: number;
  next_step: NextStep | null;
}

export interface PendingAccess {
  id: number;
  system: string;
  status: string;
  full_name: string;
}

import type {
  HealthResponse,
  SessionCreate,
  SessionCreateResponse,
  SessionDetailResponse,
  SessionListItem,
  SessionResponse,
  SessionUpdate,
  SettingsResponse,
  SettingsTestResponse,
  SettingsUpdate,
} from "@/lib/types/api";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = RequestInit & { expectEmpty?: boolean };

async function request<T>(path: string, init?: RequestOptions): Promise<T> {
  const { expectEmpty, ...rest } = init ?? {};
  const response = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(rest.headers ?? {}),
    },
    cache: "no-store",
  });

  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(
      `${response.status} ${response.statusText} on ${path}`,
      response.status,
      body,
    );
  }

  return (expectEmpty ? undefined : body) as T;
}

export const api = {
  healthz: () => request<HealthResponse>("/healthz"),

  listSessions: () => request<SessionListItem[]>("/sessions"),

  getSession: (id: string) =>
    request<SessionDetailResponse>(`/sessions/${id}`),

  createSession: (body: SessionCreate) =>
    request<SessionCreateResponse>("/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  patchSession: (id: string, body: SessionUpdate) =>
    request<SessionResponse>(`/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  deleteSession: (id: string) =>
    request<void>(`/sessions/${id}`, {
      method: "DELETE",
      expectEmpty: true,
    }),

  runSession: (id: string) =>
    request<void>(`/sessions/${id}/run`, {
      method: "POST",
    }),

  interruptSession: (id: string) =>
    request<void>(`/sessions/${id}/interrupt`, {
      method: "POST",
    }),

  getSettings: () => request<SettingsResponse>("/settings"),

  putSettings: (body: SettingsUpdate) =>
    request<SettingsResponse>("/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  testSettings: () =>
    request<SettingsTestResponse>("/settings/test", {
      method: "POST",
    }),
};

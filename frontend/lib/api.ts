// Thin fetch wrapper. Every call rides the session cookie (credentials:
// "include") — static export has no server, so the browser talks to
// FastAPI directly. Same-origin in production (Nginx serves both), so no
// CORS is involved there; NEXT_PUBLIC_API_BASE only matters for local dev
// where the Next.js dev server and FastAPI run on different ports.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.detail || message;
    } catch {
      // body wasn't JSON — keep statusText
    }
    throw new ApiError(res.status, message);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  base: API_BASE,
};

export type Role = "owner" | "admin" | "member" | "viewer";

export interface Me {
  id: number;
  username: string;
  role: Role;
}

export const ROLE_RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2, owner: 3 };

export function hasRole(me: Me | null, min: Role): boolean {
  if (!me) return false;
  return ROLE_RANK[me.role] >= ROLE_RANK[min];
}

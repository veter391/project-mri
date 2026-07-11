// Same-origin API client — the dashboard is served by FastAPI at /dashboard,
// so the API lives at /api on the same origin. JWT is kept in localStorage.

const TOKEN_KEY = "mri_token";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
}
export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    throw new ApiError(res.status, `request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

// Shape mirrors GET /api/scans: each row is `scans.*` joined with the project
// name, plus `summary` parsed from summary_json (holds overall_health once the
// scan completes). See src/mri/api/routes/scans.py::list_scans.
export interface Scan {
  scan_uuid: string;
  project_name: string;
  status: string;
  started_at: string;
  summary?: { overall_health?: number } | null;
}

export const login = (username: string, password: string) =>
  api<{ token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

export const listScans = () => api<{ scans: Scan[]; count: number }>("/scans?limit=20");

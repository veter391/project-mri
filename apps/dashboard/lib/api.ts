// Same-origin API client — the dashboard is served by FastAPI at /dashboard,
// so the API lives at /api on the same origin. JWT is kept in localStorage.
import type { components } from "./api-types";

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

// Types are generated from the API's own OpenAPI schema — never hand-written.
// Regenerate with `pnpm types:api` from the repo root; CI fails if the checked-in
// output drifts from the schema.
export type Scan = components["schemas"]["ScanSummary"];
export type ScanListResponse = components["schemas"]["ScanListResponse"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type Project = components["schemas"]["ProjectSummary"];
export type ProjectListResponse = components["schemas"]["ProjectListResponse"];

// GET /api/projects/{id}/fusion returns a plain object (no Pydantic response
// model), so it is not in the generated schema — typed here to the endpoint's
// stable shape. Each factor's `statement` is the honest human sentence the
// backend built; the UI renders it verbatim, it does not paraphrase.
export interface FusionFactor {
  name: string;
  statement: string;
  value: unknown;
}
export interface FusionFile {
  file: string;
  prose: string;
  factors: FusionFactor[];
}
export interface FusionResponse {
  project_id: number;
  project: string;
  files: FusionFile[];
}

export const login = (username: string, password: string) =>
  api<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });

export const listScans = () => api<ScanListResponse>("/scans?limit=20");
export const listProjects = () => api<ProjectListResponse>("/projects?limit=50");
export const getFusion = (projectId: number, top = 25) =>
  api<FusionResponse>(`/projects/${projectId}/fusion?top=${top}`);

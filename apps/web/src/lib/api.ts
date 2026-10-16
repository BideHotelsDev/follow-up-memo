import type { Schemas } from "@bide-followup/shared-types"

export type User = Schemas["UserOut"]
export type UserIn = Schemas["UserIn"]
export type Providers = Schemas["ProvidersOut"]
export type Connections = Schemas["ConnectionsOut"]
export type Connection = Schemas["ConnectionOut"]

/** An API error: the HTTP status, the domain `code` from a problem-details body, and a readable message. */
export class HttpError extends Error {
  status: number
  code?: string

  constructor(status: number, message: string, code?: string) {
    super(message)
    this.name = "HttpError"
    this.status = status
    this.code = code
  }
}

/** Pull something readable out of FastAPI's error shapes (problem details, HTTPException, 422 validation). */
function readDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null) return fallback
  const detail = (body as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: string[] } | undefined
    if (first?.msg) {
      const field = first.loc?.filter((p) => p !== "body").join(".")
      return field ? `${field}: ${first.msg}` : first.msg
    }
  }
  return fallback
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  // Same origin in dev (Vite proxy) and production (the API serves the app), so the session cookie just works.
  const resp = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (resp.status === 204) return undefined as T
  const data = resp.headers.get("content-type")?.includes("json") ? await resp.json() : undefined
  if (!resp.ok) {
    throw new HttpError(resp.status, readDetail(data, resp.statusText), (data as { code?: string })?.code)
  }
  return data as T
}

export const api = {
  me: () => request<User>("GET", "/auth/me"),
  providers: () => request<Providers>("GET", "/auth/providers"),
  devLogin: (email: string) => request<void>("POST", "/auth/dev-login", { email }),
  logout: () => request<void>("POST", "/auth/logout"),

  connections: () => request<Connections>("GET", "/admin/connections"),
  people: () => request<User[]>("GET", "/admin/people"),
  addPerson: (body: UserIn) => request<User>("POST", "/admin/people", body),
  updatePerson: (id: string, body: UserIn) => request<User>("PUT", `/admin/people/${id}`, body),
}

/** Full-page navigations (OAuth redirects), not fetches. */
export const links = {
  googleSignIn: (next = "/") => `/api/auth/google/login?next=${encodeURIComponent(next)}`,
  googleConnect: (loginHint?: string) =>
    `/api/auth/google/connect${loginHint ? `?login_hint=${encodeURIComponent(loginHint)}` : ""}`,
  slackInstall: () => "/api/auth/slack/install",
}

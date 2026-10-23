import type { Schemas } from "@bide-followup/shared-types"

export type User = Schemas["UserOut"]
export type UserIn = Schemas["UserIn"]
export type Providers = Schemas["ProvidersOut"]
export type Connections = Schemas["ConnectionsOut"]
export type Connection = Schemas["ConnectionOut"]
export type Person = Schemas["PersonOut"]
export type Today = Schemas["TodayOut"]
export type MeetingSummary = Schemas["MeetingSummaryOut"]
export type Meeting = Schemas["MeetingOut"]
export type Task = Schemas["TaskOut"]
export type TaskIn = Schemas["TaskIn"]
export type Question = Schemas["QuestionOut"]
export type AnswerIn = Schemas["AnswerIn"]
export type Output = Schemas["OutputOut"]
export type OutputIn = Schemas["OutputIn"]
export type Run = Schemas["RunOut"]
export type Notice = Schemas["NoticeOut"]
export type Preview = Schemas["PreviewOut"]
export type Impact = Schemas["ImpactOut"]
export type ClaudeStatus = Schemas["ClaudeStatusOut"]
export type AppSettings = Schemas["AppOut"]
export type DictationToken = Schemas["DictationTokenOut"]
export type Property = Schemas["PropertyOut"]
export type PropertyIn = Schemas["PropertyIn"]
export type System = Schemas["SystemOut"]
export type Category = Schemas["CategoryOut"]
export type CategoryIn = Schemas["CategoryIn"]
export type Settings = Schemas["SettingsOut"]
export type SettingsIn = Schemas["SettingsIn"]
export type ChannelMap = Schemas["ChannelMapOut"]
export type ChannelMapIn = Schemas["ChannelMapIn"]
export type SkipRule = Schemas["SkipRuleOut"]
export type SkipRuleIn = Schemas["SkipRuleIn"]

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

/** A query string from the set values only. */
function qs(params: Record<string, string | null | undefined>): string {
  const entries = Object.entries(params).filter((e): e is [string, string] => Boolean(e[1]))
  return entries.length ? `?${new URLSearchParams(entries)}` : ""
}

/** The filter every review page shares: a property name, or "Bide-wide" for meetings tagged with none. */
export type Scope = { property?: string | null }

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

  app: () => request<AppSettings>("GET", "/app"),
  people: () => request<Person[]>("GET", "/people"),
  impact: (params: { property?: string | null; weeks?: string }) => request<Impact>("GET", `/impact${qs(params)}`),
  today: (scope: Scope) => request<Today>("GET", `/today${qs(scope)}`),
  meetings: (params: Scope & { q?: string; person?: string; category?: string }) =>
    request<MeetingSummary[]>("GET", `/meetings${qs(params)}`),
  meeting: (id: string) => request<Meeting>("GET", `/meetings/${id}`),
  reprocess: (id: string) => request<Meeting>("POST", `/meetings/${id}/reprocess`),
  outputs: (params: Scope & { type?: string; status?: string }) => request<Output[]>("GET", `/outputs${qs(params)}`),
  editOutput: (id: string, body: OutputIn) => request<Output>("PATCH", `/outputs/${id}`, body),
  approve: (id: string) => request<Output>("POST", `/outputs/${id}/approve`),
  approveAll: (meetingId?: string) =>
    request<Output[]>("POST", "/outputs/approve-all", { meeting_id: meetingId ?? null }),
  discard: (id: string) => request<Output>("POST", `/outputs/${id}/discard`),
  tasks: (params: Scope & { owner?: string; q?: string; category?: string }) =>
    request<Task[]>("GET", `/tasks${qs(params)}`),
  updateTask: (id: string, body: TaskIn) => request<Task>("PATCH", `/tasks/${id}`, body),
  answer: (id: string, body: AnswerIn) => request<Question>("POST", `/questions/${id}/answer`, body),
  reopen: (id: string) => request<Question>("POST", `/questions/${id}/reopen`),

  connections: () => request<Connections>("GET", "/admin/connections"),
  claude: () => request<ClaudeStatus>("GET", "/admin/claude"),
  claudeMode: (mode: ClaudeStatus["mode"]) => request<ClaudeStatus>("PUT", "/admin/claude/mode", { mode }),
  routineToken: () => request<{ token: string }>("POST", "/admin/claude/routine-token"),
  revokeRoutineToken: () => request<void>("DELETE", "/admin/claude/routine-token"),
  slackTest: () => request<Schemas["SlackTestOut"]>("POST", "/admin/slack/test"),
  dictationToken: () => request<DictationToken>("POST", "/dictation/token"),
  adminPeople: () => request<User[]>("GET", "/admin/people"),
  addPerson: (body: UserIn) => request<User>("POST", "/admin/people", body),
  updatePerson: (id: string, body: UserIn) => request<User>("PUT", `/admin/people/${id}`, body),
  settings: () => request<Settings>("GET", "/admin/settings"),
  putSettings: (body: SettingsIn) => request<Settings>("PUT", "/admin/settings", body),
  channels: () => request<ChannelMap[]>("GET", "/admin/channels"),
  putChannels: (body: ChannelMapIn[]) => request<ChannelMap[]>("PUT", "/admin/channels", body),
  skipRules: () => request<SkipRule[]>("GET", "/admin/skip-rules"),
  putSkipRules: (body: SkipRuleIn[]) => request<SkipRule[]>("PUT", "/admin/skip-rules", body),
  runs: () => request<Run[]>("GET", "/admin/runs"),
  adminProperties: () => request<Property[]>("GET", "/admin/properties"),
  addProperty: (body: PropertyIn) => request<Property>("POST", "/admin/properties", body),
  updateProperty: (id: string, body: PropertyIn) => request<Property>("PUT", `/admin/properties/${id}`, body),
  adminCategories: () => request<Category[]>("GET", "/admin/categories"),
  addCategory: (body: CategoryIn) => request<Category>("POST", "/admin/categories", body),
  updateCategory: (id: string, body: CategoryIn) => request<Category>("PUT", `/admin/categories/${id}`, body),
  adminSystems: () => request<System[]>("GET", "/admin/systems"),
  addSystem: (body: PropertyIn) => request<System>("POST", "/admin/systems", body),
  updateSystem: (id: string, body: PropertyIn) => request<System>("PUT", `/admin/systems/${id}`, body),
  notices: () => request<Notice[]>("GET", "/admin/notices"),
  digestPreview: () => request<Preview>("GET", "/admin/digest-preview"),
  reminderPreview: () => request<Preview>("GET", "/admin/reminder-preview"),
  undatedPreview: () => request<Preview>("GET", "/admin/undated-preview"),
  runNow: () => request<Run>("POST", "/admin/runs"),
}

/** Full-page navigations (OAuth redirects), not fetches. */
export const links = {
  googleSignIn: (next = "/") => `/api/auth/google/login?next=${encodeURIComponent(next)}`,
  googleConnect: (loginHint?: string) =>
    `/api/auth/google/connect${loginHint ? `?login_hint=${encodeURIComponent(loginHint)}` : ""}`,
  slackInstall: () => "/api/auth/slack/install",
}

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, ExternalLink, KeyRound } from "lucide-react"
import { Link, useSearchParams } from "react-router-dom"
import { toast } from "sonner"

import { CopyButton, CopyField } from "@/components/copy"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { useApp } from "@/hooks/use-app"
import { api, HttpError, links, type Connection } from "@/lib/api"
import { day, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const ERRORS: Record<string, string> = {
  scopes_missing: "Google didn't grant every permission. Connect again and tick all the boxes.",
  no_refresh_token: "Google didn't return offline access. Connect again.",
  invalid_state: "The connection took too long or was opened in another tab. Try again.",
  google_error: "Google didn't complete the connection. Try again.",
  slack_error: "Slack didn't complete the install. Try again.",
}

function Status({ row }: { row: Connection | null | undefined }) {
  if (!row) return <Badge variant="outline">Not connected</Badge>
  if (row.status === "connected") return <Badge className="bg-ok-subtle text-ok-foreground">Connected</Badge>
  return <Badge variant="destructive">{row.status === "revoked" ? "Access revoked" : "Error"}</Badge>
}

const ROUTINES_URL = "https://claude.ai/code/routines"

function Step({ n, done, title, children }: { n: number; done: boolean; title: string; children?: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[1.75rem_1fr] gap-3">
      <span
        aria-hidden
        className={cn(
          "tnum grid size-7 place-items-center rounded-full border text-sm font-medium",
          done ? "border-transparent bg-ok text-white" : "bg-card text-foreground",
        )}
      >
        {done ? <Check className="size-4" /> : n}
      </span>
      <div className="grid min-w-0 gap-3 pt-0.5">
        <p className="font-medium text-foreground">
          {title}
          <span className="sr-only">{done ? " (done)" : ""}</span>
        </p>
        {children}
      </div>
    </li>
  )
}

function ClaudeCard() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ["claude"], queryFn: api.claude, refetchInterval: 30_000 })
  const [token, setToken] = useState<string | null>(null)
  const fail = (err: unknown) => toast.error(err instanceof HttpError ? err.message : "Couldn't save")
  const mode = useMutation({
    mutationFn: api.claudeMode,
    onSuccess: (status) => queryClient.setQueryData(["claude"], status),
    onError: fail,
  })
  const make = useMutation({
    mutationFn: api.routineToken,
    onSuccess: ({ token }) => {
      setToken(token)
      queryClient.invalidateQueries({ queryKey: ["claude"] })
    },
    onError: fail,
  })
  if (!data) return null
  const routine = data.mode === "routine"
  const stuck = data.oldest_pending_at && Date.now() - new Date(data.oldest_pending_at).getTime() > 3 * 3600_000
  const seen = data.routine_seen_at
  const when = (iso: string) => `${day(localDate(iso))} ${time(iso)}`

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>Claude</CardTitle>
          {!data.enabled ? (
            <Badge variant="outline">Not connected</Badge>
          ) : stuck ? (
            <Badge variant="destructive">Routine not answering</Badge>
          ) : routine && !seen ? (
            <Badge className="bg-attention-subtle text-attention-foreground">Waiting for the routine</Badge>
          ) : (
            <Badge className="bg-ok-subtle text-ok-foreground">Connected</Badge>
          )}
        </div>
        <CardDescription>
          Claude reads the notes and writes the emails. Either through the Claude API (billed per use) or a scheduled
          Claude Code routine on Bide’s Claude plan (no API bill, drafts within about an hour).
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6">
        <div role="radiogroup" aria-label="How the app reaches Claude" className="grid gap-2 sm:grid-cols-2">
          {(
            [
              ["api", "Claude API", data.api_key_set ? "Uses ANTHROPIC_API_KEY" : "Needs ANTHROPIC_API_KEY on Railway"],
              ["routine", "Claude Code routine", "Runs hourly on Bide’s Claude plan"],
            ] as const
          ).map(([key, label, note]) => (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={data.mode === key}
              disabled={mode.isPending}
              onClick={() => data.mode !== key && mode.mutate(key)}
              className={cn(
                "grid gap-0.5 rounded-lg border bg-card px-4 py-3 text-left transition hover:border-foreground/30",
                data.mode === key && "border-primary shadow-[inset_3px_0_0_var(--primary)]",
              )}
            >
              <span className="font-medium text-foreground">{label}</span>
              <span className="text-sm text-muted-foreground">{note}</span>
            </button>
          ))}
        </div>

        {routine ? (
          <ol className="grid gap-6">
            <Step n={1} done={data.routine_token_set} title="Make a token for the routine">
              {token ? (
                <div className="grid gap-2">
                  <CopyField name="FOLLOWUP_TOKEN" value={token} secret />
                  <p className="text-sm text-attention-foreground dark:text-attention">
                    Copy it now: it isn’t shown again. Making a new one switches this one off.
                  </p>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    variant={data.routine_token_set ? "outline" : "default"}
                    disabled={make.isPending}
                    onClick={() =>
                      (!data.routine_token_set ||
                        window.confirm("Make a new token? The routine’s current token stops working.")) &&
                      make.mutate()
                    }
                  >
                    <KeyRound className="size-4" aria-hidden />
                    {data.routine_token_set ? "Make a new token" : "Make a token"}
                  </Button>
                  {data.routine_token_set ? (
                    <span className="text-sm text-muted-foreground">A token is set. It was shown once.</span>
                  ) : null}
                </div>
              )}
            </Step>
            <Step n={2} done={Boolean(seen)} title="Create the routine in Claude Code">
              <p className="text-sm text-muted-foreground">
                New routine, no repository, tools Bash, Read and Write. Put the two values below in the routine’s
                environment variables (never in the prompt), paste the prompt, and set the schedule.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <CopyField name="FOLLOWUP_URL" value={data.app_url} />
                <CopyField name="Schedule (UTC, hourly on weekdays)" value={data.routine_schedule} />
              </div>
              <div className="flex flex-wrap gap-2">
                <CopyButton text={data.routine_prompt} label="Copy the prompt" what="prompt" />
                <Button asChild>
                  <a href={ROUTINES_URL} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" aria-hidden /> Open Claude Code routines
                  </a>
                </Button>
              </div>
            </Step>
            <Step n={3} done={Boolean(seen)} title="Run it once to check">
              <p className="text-sm text-muted-foreground">
                {seen
                  ? `Connected. Last check-in ${when(seen)}.`
                  : "Press Run now on the routine. This turns green when it reaches the app (checked every 30 seconds)."}
              </p>
              <p className="text-sm text-muted-foreground">
                {data.pending ? `${data.pending} request${data.pending === 1 ? "" : "s"} waiting` : "Nothing waiting"}
                {data.oldest_pending_at ? `, oldest from ${time(data.oldest_pending_at)}` : ""}
                {data.last_answer_at ? ` · last answer ${when(data.last_answer_at)}` : ""}
              </p>
            </Step>
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">
            {data.api_key_set
              ? `Model ${data.model}.`
              : "Set ANTHROPIC_API_KEY on both Railway services to turn it on, or use the Claude Code routine instead."}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

/** Wispr Flow is a dictation app on David's computer and phone: it types into any box, so there is nothing to connect. */
function WisprCard() {
  const app = useApp()
  const words = [...new Set([...app.people, ...app.properties.map((p) => p.name), ...app.systems, "Bide"])]
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Wispr Flow</CardTitle>
          <Badge className="bg-ok-subtle text-ok-foreground">Ready</Badge>
        </div>
        <CardDescription>
          {app.owner_name}’s dictation app. It types wherever the cursor is, so it works in every box here with nothing
          to connect: answers, and edits to email and Slack drafts. ⌘ Enter (or Ctrl Enter) saves.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 text-sm">
        <p className="text-muted-foreground">Add these to Wispr’s Dictionary so names are spelled right:</p>
        <p className="text-foreground">{words.join(", ")}</p>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        <CopyButton text={words.join("\n")} label="Copy the names" what="names" />
        <Button asChild variant="ghost">
          <Link to="/how#wispr">How to dictate</Link>
        </Button>
      </CardFooter>
    </Card>
  )
}

export default function ConnectionsPage() {
  const { owner_name: owner, owner_email } = useApp()
  const [params] = useSearchParams()
  const { data } = useQuery({ queryKey: ["connections"], queryFn: api.connections })
  const error = params.get("error")

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-2xl">Connections</h2>
        <p className="text-muted-foreground">
          The app reads {owner}’s meeting notes and writes Gmail drafts as {owner}, and posts approved messages as the
          bot. Claude reads the notes. Each is set up once.
        </p>
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{ERRORS[error] ?? "Something went wrong. Try again."}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>{owner}’s Google account</CardTitle>
              <Status row={data?.google} />
            </div>
            <CardDescription>
              Drive (read notes), Calendar (read attendees) and Gmail (create drafts). {owner} signs in with their own
              account on the Google screen.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {data?.google ? <p>Connected as {data.google.account_email}</p> : null}
            {data?.google?.last_error ? <p className="text-destructive">{data.google.last_error}</p> : null}
          </CardContent>
          <CardFooter>
            <Button asChild>
              <a href={links.googleConnect(owner_email ?? undefined)}>
                {data?.google ? "Reconnect" : "Connect"} Google
              </a>
            </Button>
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>Slack bot</CardTitle>
              <Status row={data?.slack} />
            </div>
            <CardDescription>
              Sends {owner} the run summary and posts team messages after {owner} approves them.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {data?.slack ? <p>Installed in {data.slack.account_email}</p> : null}
          </CardContent>
          <CardFooter>
            <Button asChild variant={data?.slack ? "outline" : "default"}>
              <a href={links.slackInstall()}>{data?.slack ? "Reinstall" : "Install"} Slack bot</a>
            </Button>
          </CardFooter>
        </Card>
        <WisprCard />
        <ClaudeCard />
      </div>
    </div>
  )
}

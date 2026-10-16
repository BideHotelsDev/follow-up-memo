import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { api, links, type Connection } from "@/lib/api"
import { day, localDate, time } from "@/lib/format"

const ERRORS: Record<string, string> = {
  scopes_missing: "Google didn't grant every permission. Connect again and tick all the boxes.",
  no_refresh_token: "Google didn't return offline access. Connect again.",
  invalid_state: "The connection took too long or was opened in another tab. Try again.",
  google_error: "Google didn't complete the connection. Try again.",
  slack_error: "Slack didn't complete the install. Try again.",
}

const DAVID = "david@liddellpropertyinvestments.com"

function Status({ row }: { row: Connection | null | undefined }) {
  if (!row) return <Badge variant="outline">Not connected</Badge>
  if (row.status === "connected") return <Badge className="bg-ok-subtle text-ok-foreground">Connected</Badge>
  return <Badge variant="destructive">{row.status === "revoked" ? "Access revoked" : "Error"}</Badge>
}

function ClaudeCard() {
  const { data } = useQuery({ queryKey: ["claude"], queryFn: api.claude, refetchInterval: 60_000 })
  if (!data) return null
  const routine = data.mode === "routine"
  const stuck = data.oldest_pending_at && Date.now() - new Date(data.oldest_pending_at).getTime() > 3 * 3600_000
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Claude</CardTitle>
          {!data.enabled ? (
            <Badge variant="outline">Off</Badge>
          ) : stuck ? (
            <Badge variant="destructive">Routine not answering</Badge>
          ) : (
            <Badge className="bg-ok-subtle text-ok-foreground">On</Badge>
          )}
        </div>
        <CardDescription>
          {routine
            ? "Reads the notes and writes the emails through a scheduled Claude Code routine on Bide’s Claude plan."
            : "Reads the notes and writes the emails through the Claude API."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-1 text-sm">
        <p>{data.model}</p>
        {routine ? (
          <>
            <p className="text-muted-foreground">
              {data.pending ? `${data.pending} request${data.pending === 1 ? "" : "s"} waiting` : "Nothing waiting"}
              {data.oldest_pending_at ? `, oldest from ${time(data.oldest_pending_at)}` : ""}
            </p>
            <p className="text-muted-foreground">
              {data.last_answer_at
                ? `Last answer ${day(localDate(data.last_answer_at))} ${time(data.last_answer_at)}`
                : "No answers yet"}
            </p>
          </>
        ) : null}
        {!data.enabled ? (
          <p className="text-muted-foreground">
            {routine
              ? "Set SERVICE_API_TOKEN and set up the routine (routine/README.md)."
              : "Set ANTHROPIC_API_KEY to turn it on."}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

export default function ConnectionsPage() {
  const [params] = useSearchParams()
  const { data } = useQuery({ queryKey: ["connections"], queryFn: api.connections })
  const error = params.get("error")

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-2xl">Connections</h2>
        <p className="text-muted-foreground">
          The app reads David's meeting notes and writes Gmail drafts as David, and posts approved messages as the bot.
          Both are set up once.
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
              <CardTitle>David's Google account</CardTitle>
              <Status row={data?.google} />
            </div>
            <CardDescription>
              Drive (read notes), Calendar (read attendees) and Gmail (create drafts). David signs in with his own
              account on the Google screen.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {data?.google ? <p>Connected as {data.google.account_email}</p> : null}
            {data?.google?.last_error ? <p className="text-destructive">{data.google.last_error}</p> : null}
          </CardContent>
          <CardFooter>
            <Button asChild>
              <a href={links.googleConnect(DAVID)}>{data?.google ? "Reconnect" : "Connect"} Google</a>
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
              Sends David his run summary and posts team messages after David approves them.
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
        <ClaudeCard />
      </div>
    </div>
  )
}

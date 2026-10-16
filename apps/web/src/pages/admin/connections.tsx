import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { api, links, type Connection } from "@/lib/api"

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
      </div>
    </div>
  )
}

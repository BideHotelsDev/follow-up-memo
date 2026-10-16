import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink, RotateCw } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { Empty, Loading, PageHead, surface } from "@/components/page"
import { HotelTags, MeetingStatus } from "@/components/tags"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useScope } from "@/hooks/use-scope"
import { api, HttpError, type Meeting, type MeetingSummary } from "@/lib/api"
import { day, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const OUTPUT_PAGE: Record<string, [string, string]> = {
  email_draft: ["/emails", "Email draft"],
  slack_dm: ["/slack", "Slack DM"],
  slack_digest: ["/slack", "Channel update"],
}

function Point({
  kind,
  question,
  children,
  to,
}: {
  kind: string
  question?: boolean
  children: React.ReactNode
  to?: [string, string]
}) {
  return (
    <li className="grid gap-1 border-t py-3 first:border-t-0 sm:grid-cols-[6rem_1fr_auto] sm:items-baseline sm:gap-4">
      <span
        className={cn(
          "text-xs font-semibold tracking-[0.08em] uppercase",
          question ? "text-attention-foreground dark:text-attention" : "text-muted-foreground",
        )}
      >
        {kind}
      </span>
      <span className="text-foreground">{children}</span>
      {to ? (
        <Link to={to[0]} className="text-sm whitespace-nowrap text-muted-foreground underline underline-offset-2">
          {to[1]}
        </Link>
      ) : (
        <span />
      )}
    </li>
  )
}

function Detail({ meeting }: { meeting: Meeting }) {
  const queryClient = useQueryClient()
  const reprocess = useMutation({
    mutationFn: () => api.reprocess(meeting.id),
    onSuccess: () => {
      queryClient.invalidateQueries()
      toast.success("Reprocessed. Drafts you hadn’t acted on were replaced.")
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't reprocess"),
  })
  const outputsByType = (type: string) => meeting.outputs.filter((o) => o.type === type && o.status !== "discarded")
  const hasEmail = outputsByType("email_draft").length > 0
  const dmTo = new Set(outputsByType("slack_dm").map((o) => o.recipient_label))

  return (
    <article className={surface}>
      <div className="grid gap-3 border-b p-5 md:p-6">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <HotelTags properties={meeting.properties} />
          <MeetingStatus status={meeting.status} />
          {meeting.is_sensitive ? (
            <span className="text-sm text-muted-foreground">Sensitive: no team messages</span>
          ) : null}
        </div>
        <h2 className="text-3xl">{meeting.title}</h2>
        <p className="tnum text-sm text-muted-foreground">
          {day(localDate(meeting.started_at))} · {time(meeting.started_at)}
          {meeting.ended_at ? `–${time(meeting.ended_at)}` : ""} · Notes by Gemini
        </p>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
          {meeting.attendees.map((a) => (
            <span key={`${a.name}${a.email}`} className="inline-flex items-center gap-2">
              <span
                aria-hidden
                className={cn(
                  "inline-grid size-6 place-items-center rounded-full border text-xs font-medium",
                  a.is_internal ? "bg-secondary" : "border-dashed bg-card",
                )}
              >
                {a.name.slice(0, 1)}
              </span>
              {a.name}
              {!a.is_internal ? <span className="text-muted-foreground">· external</span> : null}
            </span>
          ))}
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button asChild variant="outline" size="sm">
            <a href={meeting.notes_url} target="_blank" rel="noreferrer">
              <ExternalLink className="size-4" aria-hidden /> Open the notes
            </a>
          </Button>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" size="sm" disabled={reprocess.isPending}>
                <RotateCw className={cn("size-4", reprocess.isPending && "animate-spin")} aria-hidden />
                {reprocess.isPending ? "Reprocessing…" : "Reprocess"}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reprocess {meeting.title}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Claude reads the notes again. Drafts you haven’t approved, edited or discarded are replaced; anything
                  you already acted on stays as it is. Answers to questions are cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={() => reprocess.mutate()}>Reprocess</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
      <div className="grid gap-5 p-5 md:p-6">
        {meeting.status === "skipped" ? (
          <p className="rounded-lg bg-secondary p-4">{meeting.skip_reason ?? "Skipped."}</p>
        ) : meeting.status === "queued" || meeting.status === "processing" ? (
          <p className="rounded-lg bg-attention-subtle p-4 text-foreground">Waiting for the next run.</p>
        ) : meeting.status === "failed" ? (
          <p className="rounded-lg bg-danger-subtle p-4 text-foreground">
            This meeting couldn’t be processed after three tries.{" "}
            {meeting.error ? <span className="text-muted-foreground">({meeting.error.split(":")[0]})</span> : null}{" "}
            Reprocess it, or open the notes.
          </p>
        ) : (
          <>
            {meeting.purpose ? <p className="max-w-prose text-lg text-foreground">{meeting.purpose}</p> : null}
            {meeting.notes_quality && meeting.notes_quality !== "good" ? (
              <p className="rounded-lg bg-attention-subtle p-3 text-sm text-foreground">
                The notes were {meeting.notes_quality === "thin" ? "thin" : "hard to follow"}, so there may be less here
                than was said.
              </p>
            ) : null}
            <ul>
              {meeting.decisions.map((d) => (
                <Point key={d} kind="Decided">
                  {d}
                </Point>
              ))}
              {meeting.tasks.map((t) => {
                const owner = t.owner?.name ?? t.owner_name
                const to: [string, string] | undefined =
                  t.owner && dmTo.has(t.owner.name)
                    ? ["/slack", "Slack draft"]
                    : t.owner?.role === "owner"
                      ? ["/tasks", "Task list"]
                      : !t.owner && t.owner_name && hasEmail
                        ? ["/emails", "Email draft"]
                        : undefined
                return (
                  <Point key={t.id} kind={owner ? owner.split(" ")[0] : "Needs David"} question={!owner} to={to}>
                    {t.description}
                    {t.due_date ? <span className="tnum text-muted-foreground"> · {day(t.due_date)}</span> : null}
                  </Point>
                )
              })}
              {meeting.questions
                .filter((q) => !q.answered_at)
                .map((q) => (
                  <Point key={q.id} kind="Question" question to={["/", "For you"]}>
                    {q.text}
                  </Point>
                ))}
              {meeting.key_points.map((k) => (
                <Point key={k} kind="Note">
                  {k}
                </Point>
              ))}
            </ul>
            {meeting.outputs.length ? (
              <div className="flex flex-wrap gap-2 text-sm">
                {meeting.outputs.map((o) => {
                  const page = OUTPUT_PAGE[o.type]
                  return page ? (
                    <Link key={o.id} to={page[0]} className="rounded-full border px-3 py-1 hover:border-foreground">
                      {page[1]} · {o.recipient_label}
                      <span className="text-muted-foreground">
                        {" "}
                        · {o.status === "draft" ? "waiting" : o.status.replaceAll("_", " ")}
                      </span>
                    </Link>
                  ) : null
                })}
              </div>
            ) : null}
            {meeting.dropped_actions.length ? (
              <details className="text-sm text-muted-foreground">
                <summary className="cursor-pointer">
                  Left out ({meeting.dropped_actions.length}): Claude suggested these, but the notes don’t back them up
                </summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {meeting.dropped_actions.map((d) => (
                    <li key={d}>{d}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </>
        )}
      </div>
    </article>
  )
}

function Item({ m, selected }: { m: MeetingSummary; selected: boolean }) {
  return (
    <Link
      to={`/meetings/${m.id}`}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "grid gap-1.5 rounded-lg border bg-card px-4 py-3 hover:border-foreground/30",
        selected && "border-primary shadow-[inset_3px_0_0_var(--primary)]",
      )}
    >
      <span className="flex items-baseline justify-between gap-3">
        <b className="font-medium text-foreground">{m.title}</b>
        <span className="tnum text-sm text-muted-foreground">{time(m.started_at)}</span>
      </span>
      <span className="flex flex-wrap items-center gap-2">
        <HotelTags properties={m.properties} />
        <MeetingStatus status={m.status} />
      </span>
    </Link>
  )
}

export default function MeetingsPage() {
  const { id } = useParams()
  const { scope } = useScope()
  const [q, setQ] = useState("")
  const list = useQuery({
    queryKey: ["meetings", scope.property, q],
    queryFn: () => api.meetings({ property: scope.property, q }),
  })
  const selectedId = id ?? list.data?.[0]?.id
  const detail = useQuery({
    queryKey: ["meeting", selectedId],
    queryFn: () => api.meeting(selectedId!),
    enabled: Boolean(selectedId),
  })

  const today = localDate(new Date().toISOString())
  const groups = new Map<string, MeetingSummary[]>()
  for (const m of list.data ?? []) {
    const key = localDate(m.started_at) ?? ""
    groups.set(key, [...(groups.get(key) ?? []), m])
  }

  return (
    <>
      <PageHead title="Meetings" lede="What Gemini recorded, and where every point ended up." />
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
        <div className="grid gap-5">
          <Input
            type="search"
            placeholder="Search meetings"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search meetings"
            className="bg-card"
          />
          {list.isPending ? (
            <Loading />
          ) : groups.size ? (
            [...groups].map(([date, meetings]) => (
              <div key={date}>
                <h4 className="eyebrow mb-2 text-muted-foreground">{date === today ? "Today" : day(date)}</h4>
                <div className="grid gap-2">
                  {meetings.map((m) => (
                    <Item key={m.id} m={m} selected={m.id === selectedId} />
                  ))}
                </div>
              </div>
            ))
          ) : (
            <Empty>No meetings{q ? " match" : " yet"}.</Empty>
          )}
        </div>
        <div className="md:sticky md:top-32">
          {detail.data ? <Detail meeting={detail.data} /> : selectedId ? <Loading /> : null}
        </div>
      </div>
    </>
  )
}

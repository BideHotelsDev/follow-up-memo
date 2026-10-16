import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { Mrkdwn } from "@/components/mrkdwn"
import { Empty, Loading, PageHead, surface } from "@/components/page"
import { HotelTags, Status } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Textarea } from "@/components/ui/textarea"
import { useScope } from "@/hooks/use-scope"
import { api, HttpError, type Output } from "@/lib/api"
import { dayOf, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const fail = (err: unknown) => toast.error(err instanceof HttpError ? err.message : "Something went wrong")

function Message({ draft }: { draft: Output }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(draft.body)
  const channel = draft.type === "slack_digest"
  const waiting = draft.status === "draft"
  const refresh = () => queryClient.invalidateQueries()
  const approve = useMutation({
    mutationFn: () => api.approve(draft.id),
    onSuccess: () => {
      refresh()
      toast.success(channel ? `Posted to ${draft.recipient_label}` : `Sent to ${draft.recipient_label}`)
    },
    onError: (err) => {
      refresh()
      fail(err)
    },
  })
  const save = useMutation({
    mutationFn: () => api.editOutput(draft.id, { body }),
    onSuccess: () => {
      setEditing(false)
      refresh()
    },
    onError: fail,
  })
  const discard = useMutation({ mutationFn: () => api.discard(draft.id), onSuccess: refresh, onError: fail })

  return (
    <article className={surface}>
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3 text-sm text-muted-foreground">
        <span>
          <b className="font-medium text-foreground">Slack</b> ·{" "}
          {channel ? draft.recipient_label : `DM to ${draft.recipient_label}`}
        </span>
        {draft.status === "posted" ? (
          <Status tone="done">Approved · posted</Status>
        ) : draft.status === "failed" ? (
          <Status tone="late">{draft.error ?? "Failed"}</Status>
        ) : (
          <Status tone="wait">Draft</Status>
        )}
      </div>
      <div className="grid grid-cols-[2.5rem_1fr] gap-3 p-4">
        <span
          aria-hidden
          className="font-display grid size-10 place-items-center rounded-lg border bg-secondary text-lg"
        >
          D
        </span>
        <div className="min-w-0">
          <p className="font-semibold text-foreground">David</p>
          {editing ? (
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={8}
              className="mt-1"
              aria-label="Message"
            />
          ) : (
            <div className="mt-0.5 max-w-prose text-foreground">
              <Mrkdwn text={draft.body} />
            </div>
          )}
        </div>
      </div>
      {waiting || draft.status === "failed" ? (
        <div className="flex flex-wrap gap-2 px-4 pb-4 sm:pl-[4.25rem]">
          {editing ? (
            <>
              <Button onClick={() => save.mutate()} disabled={save.isPending || !body.trim()}>
                Save
              </Button>
              <Button variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              {waiting ? (
                <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
                  {channel ? "Approve & post" : "Approve & send"}
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="ghost" onClick={() => discard.mutate()} disabled={discard.isPending}>
                Discard
              </Button>
            </>
          )}
        </div>
      ) : null}
    </article>
  )
}

export default function SlackPage() {
  const queryClient = useQueryClient()
  const { scope } = useScope()
  const { data } = useQuery({
    queryKey: ["outputs", "slack", scope.property],
    queryFn: async () => {
      const [dms, digests] = await Promise.all([
        api.outputs({ type: "slack_dm", property: scope.property }),
        api.outputs({ type: "slack_digest", property: scope.property }),
      ])
      return [...dms, ...digests]
    },
  })
  // Only what's on screen: with a property chosen, the other properties' drafts stay waiting.
  const approveAll = useMutation({
    mutationFn: async (meetingIds: string[]) => {
      const done = []
      for (const id of meetingIds) done.push(...(await api.approveAll(id)))
      return done
    },
    onSuccess: (rows) => {
      queryClient.invalidateQueries()
      toast.success(`Approved ${rows.length}`)
    },
    onError: (err) => {
      queryClient.invalidateQueries()
      fail(err)
    },
  })
  if (!data) return <Loading />

  const today = localDate(new Date().toISOString()) ?? ""
  const waiting = data.filter((d) => d.status === "draft")
  const share = data.length ? Math.round(((data.length - waiting.length) / data.length) * 100) : 0
  const byRecipient = new Map<string, number>()
  for (const d of waiting) byRecipient.set(d.recipient_label, (byRecipient.get(d.recipient_label) ?? 0) + 1)
  const meetings = new Map<string, Output[]>()
  for (const d of data) meetings.set(d.meeting?.id ?? "", [...(meetings.get(d.meeting?.id ?? "") ?? []), d])

  return (
    <>
      <PageHead
        title="Slack drafts"
        lede="Actions for the team and updates for channels, written as David. Nothing posts until it’s approved."
      />
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <aside className={cn(surface, "grid gap-4 p-5 lg:sticky lg:top-32 lg:order-last")}>
          <span className="eyebrow text-muted-foreground">Waiting for approval</span>
          <p>
            <span className="font-display tnum text-4xl text-foreground">{waiting.length}</span>{" "}
            <span className="text-muted-foreground">of {data.length}</span>
          </p>
          <Progress value={share} aria-label={`${share}% approved`} />
          <Button
            className="w-full"
            disabled={!waiting.length || approveAll.isPending}
            onClick={() => approveAll.mutate([...new Set(waiting.map((d) => d.meeting!.id))])}
          >
            {waiting.length ? `Approve all ${waiting.length}` : "All approved"}
          </Button>
          {byRecipient.size ? (
            <ul className="divide-y text-sm">
              {[...byRecipient].map(([who, n]) => (
                <li key={who} className="flex justify-between py-2">
                  <span>{who}</span>
                  <span className="tnum text-muted-foreground">{n}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </aside>
        <div className="grid gap-8">
          {meetings.size ? (
            [...meetings].map(([id, drafts]) => {
              const meeting = drafts[0].meeting
              return (
                <section key={id} className="grid gap-3">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
                    <h2 className="text-2xl">{meeting?.title}</h2>
                    {meeting ? <HotelTags properties={meeting.properties} /> : null}
                    <span className="tnum text-sm text-muted-foreground">
                      {dayOf(meeting?.started_at, today)}, {time(meeting?.started_at)}
                    </span>
                  </div>
                  {drafts.map((d) => (
                    <Message key={d.id + d.updated_at} draft={d} />
                  ))}
                </section>
              )
            })
          ) : (
            <Empty>No Slack drafts yet.</Empty>
          )}
        </div>
      </div>
    </>
  )
}

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"
import { toast } from "sonner"

import { Empty, Loading, PageHead, surface } from "@/components/page"
import { HotelTags, Status } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useScope } from "@/hooks/use-scope"
import { api, HttpError, type Output } from "@/lib/api"
import { day, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const GROUPS: [string, string, Output["status"][]][] = [
  ["waiting", "Waiting for you", ["draft", "failed"]],
  ["closed", "Sent or deleted in Gmail", ["closed_in_gmail"]],
]

function Preview({ email }: { email: Output }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [subject, setSubject] = useState(email.subject ?? "")
  const [body, setBody] = useState(email.body)
  const done = () => queryClient.invalidateQueries()
  const fail = (err: unknown) => toast.error(err instanceof HttpError ? err.message : "Something went wrong")
  const save = useMutation({
    mutationFn: () => api.editOutput(email.id, { subject, body }),
    onSuccess: () => {
      setEditing(false)
      done()
      toast.success("Saved, and the Gmail draft is updated.")
    },
    onError: fail,
  })
  const discard = useMutation({
    mutationFn: () => api.discard(email.id),
    onSuccess: () => {
      done()
      toast.success("Discarded, and removed from your Gmail drafts.")
    },
    onError: fail,
  })
  const waiting = email.status === "draft" || email.status === "failed"

  return (
    <article className={surface}>
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3 text-sm text-muted-foreground">
        <span>
          <b className="font-medium text-foreground">Gmail</b> · draft
        </span>
        {email.status === "failed" ? (
          <Status tone="late">Not in Gmail yet: retrying</Status>
        ) : email.status === "closed_in_gmail" ? (
          <Status tone="done">Sent or deleted in Gmail</Status>
        ) : (
          <Status tone="wait">Draft · not sent</Status>
        )}
      </div>
      {email.review_carefully ? (
        <p className="mx-5 mt-4 rounded-lg bg-attention-subtle px-4 py-3 text-sm text-foreground">
          Review carefully: this meeting touched on sensitive matters. Check nothing internal is in the email.
        </p>
      ) : null}
      <div className="divide-y text-[15px]">
        <div className="grid grid-cols-[4.5rem_1fr] gap-3 px-5 py-2.5">
          <span className="text-muted-foreground">To</span>
          <span className="break-all">{email.recipient}</span>
        </div>
        <div className="grid grid-cols-[4.5rem_1fr] items-center gap-3 px-5 py-2.5">
          <span className="text-muted-foreground">Subject</span>
          {editing ? (
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
          ) : (
            <span>{email.subject}</span>
          )}
        </div>
      </div>
      <div className="border-t p-5">
        {editing ? (
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={14}
            aria-label="Email"
            className="font-sans text-[15px]"
          />
        ) : (
          <p className="max-w-prose whitespace-pre-wrap text-foreground">
            {email.body || "The email hasn’t been written yet; the next run tries again."}
          </p>
        )}
      </div>
      {waiting ? (
        <div className="flex flex-wrap gap-2 px-5 pb-5">
          {editing ? (
            <>
              <Button onClick={() => save.mutate()} disabled={save.isPending || !body.trim()}>
                Save draft
              </Button>
              <Button variant="outline" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              {email.gmail_url ? (
                <Button asChild>
                  <a href={email.gmail_url} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" aria-hidden /> Open in Gmail
                  </a>
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => setEditing(true)} disabled={!email.body}>
                Edit here
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

export default function EmailsPage() {
  const { scope } = useScope()
  const { data } = useQuery({
    queryKey: ["outputs", "email_draft", scope.property],
    queryFn: () => api.outputs({ type: "email_draft", property: scope.property }),
  })
  const [selected, setSelected] = useState<string | null>(null)
  if (!data) return <Loading />
  const current = data.find((e) => e.id === selected) ?? data.find((e) => e.status !== "closed_in_gmail") ?? data[0]
  const today = localDate(new Date().toISOString())

  return (
    <>
      <PageHead
        title="Email drafts"
        lede="Follow-ups to people outside Bide. They wait in your Gmail drafts and are never sent automatically."
      />
      {data.length ? (
        <div className="grid items-start gap-6 md:grid-cols-[minmax(0,20rem)_minmax(0,1fr)]">
          <div className="grid gap-5">
            {GROUPS.map(([key, label, statuses]) => {
              const rows = data.filter((e) => statuses.includes(e.status))
              return rows.length ? (
                <div key={key}>
                  <h4 className="eyebrow mb-2 text-muted-foreground">{label}</h4>
                  <div className="grid gap-2">
                    {rows.map((e) => (
                      <button
                        key={e.id}
                        onClick={() => setSelected(e.id)}
                        aria-pressed={e.id === current?.id}
                        className={cn(
                          "grid gap-1.5 rounded-lg border bg-card px-4 py-3 text-left hover:border-foreground/30",
                          e.id === current?.id && "border-primary shadow-[inset_3px_0_0_var(--primary)]",
                        )}
                      >
                        <span className="flex items-baseline justify-between gap-3">
                          <b className="truncate font-medium text-foreground">
                            {e.recipient.split(",")[0]}
                            {e.recipient.includes(",") ? " +" : ""}
                          </b>
                          <span className="tnum shrink-0 text-sm text-muted-foreground">
                            {localDate(e.meeting?.started_at) === today
                              ? time(e.meeting?.started_at)
                              : day(localDate(e.meeting?.started_at))}
                          </span>
                        </span>
                        <span className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                          {e.meeting ? <HotelTags properties={e.meeting.properties} /> : null}
                          <span>{e.meeting?.title}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null
            })}
          </div>
          <div className="md:sticky md:top-32">
            {current ? <Preview key={current.id + current.updated_at} email={current} /> : null}
          </div>
        </div>
      ) : (
        <Empty>No emails yet. Meetings with people outside Bide get one; internal calls don’t.</Empty>
      )}
    </>
  )
}

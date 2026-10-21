import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"

import { Empty, Loading, PageHead, surface } from "@/components/page"
import { HotelTags, Status } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useScope } from "@/hooks/use-scope"
import { useApp } from "@/hooks/use-app"
import { useMe } from "@/hooks/use-me"
import { api, HttpError, type Task, type TaskIn } from "@/lib/api"
import { day, dayOf, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const BUCKETS: [Task["bucket"], string][] = [
  ["late", "Overdue"],
  ["today", "Due today"],
  ["week", "This week"],
  ["later", "Later"],
  ["nodate", "No date set"],
  ["done", "Done"],
]
const NEEDS_OWNER = "needs_david"
const ANY = "any"

function ownerLabel(t: Task, ownerName: string) {
  if (t.owner) return t.owner.name.split(" ")[0]
  if (t.owner_name) return `${t.owner_name} (external)`
  return `Needs ${ownerName}`
}

function useUpdate(task: Task) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: TaskIn) => api.updateTask(task.id, body),
    onSuccess: () => queryClient.invalidateQueries(),
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })
}

function Tick({ task }: { task: Task }) {
  const update = useUpdate(task)
  const done = task.status !== "open"
  return (
    <button
      onClick={() => update.mutate({ status: done ? "open" : "done" })}
      aria-label={done ? "Mark as not done" : "Mark as done"}
      className={cn(
        "mt-0.5 grid size-[22px] place-items-center rounded-md border-[1.5px] bg-card",
        done ? "border-ok bg-ok text-background" : "border-input",
      )}
    >
      <Check className={cn("size-3.5", done ? "opacity-100" : "opacity-0")} strokeWidth={3} />
    </button>
  )
}

function Drawer({ task, onClose, canEdit }: { task: Task; onClose: () => void; canEdit: boolean }) {
  const { owner_name } = useApp()
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled: canEdit })
  const update = useUpdate(task)
  const today = localDate(new Date().toISOString()) ?? ""
  const ownerValue = task.owner?.id ?? (task.owner_name ? "external" : NEEDS_OWNER)

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <div className="flex flex-wrap items-center gap-2">
            <HotelTags properties={task.meeting.properties} />
            {task.bucket === "late" ? (
              <Status tone="late">Overdue</Status>
            ) : task.bucket === "done" ? (
              <Status tone="done">Done</Status>
            ) : (
              <Status tone="quiet">Open</Status>
            )}
          </div>
          <SheetTitle className="text-2xl">{task.description}</SheetTitle>
          <SheetDescription className="sr-only">Change the owner, due date or status of this task.</SheetDescription>
        </SheetHeader>
        <div className="grid content-start gap-6 overflow-y-auto p-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label className="eyebrow text-muted-foreground">Owner</Label>
              {canEdit ? (
                <Select
                  value={ownerValue}
                  onValueChange={(v) =>
                    v !== "external" && update.mutate({ owner_user_id: v === NEEDS_OWNER ? null : v })
                  }
                >
                  <SelectTrigger className="w-full bg-card" aria-label="Owner">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(people.data ?? [])
                      .filter((p) => p.role !== "admin")
                      .map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                    {task.owner_name ? <SelectItem value="external">{task.owner_name} (external)</SelectItem> : null}
                    <SelectItem value={NEEDS_OWNER}>Needs {owner_name}</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <span>{ownerLabel(task, owner_name)}</span>
              )}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="due" className="eyebrow text-muted-foreground">
                Due
              </Label>
              {canEdit ? (
                <Input
                  id="due"
                  type="date"
                  className="bg-card"
                  defaultValue={task.due_date ?? ""}
                  onBlur={(e) =>
                    (e.target.value || null) !== task.due_date && update.mutate({ due_date: e.target.value || null })
                  }
                />
              ) : (
                <span>{day(task.due_date)}</span>
              )}
            </div>
          </div>
          <div className="grid gap-2 rounded-lg border bg-card p-4">
            <span className="text-sm text-muted-foreground">
              From the notes of <b className="font-medium text-foreground">{task.meeting.title}</b> ·{" "}
              {dayOf(task.meeting.started_at, today).toLowerCase()}, {time(task.meeting.started_at)}
            </span>
            {task.source_quote ? (
              <blockquote className="border-l-[3px] border-primary pl-3 text-foreground">
                {task.source_quote}
              </blockquote>
            ) : null}
            {canEdit ? (
              <Link
                to={`/meetings/${task.meeting.id}`}
                className="justify-self-start text-sm underline underline-offset-2"
              >
                Open the meeting
              </Link>
            ) : null}
          </div>
          {canEdit && task.owner_name && !task.owner ? (
            <p className="text-sm text-muted-foreground">
              {task.owner_name} is outside Bide, so this appears in the follow-up email rather than in Slack.
            </p>
          ) : null}
        </div>
        <SheetFooter className="border-t bg-card">
          <Button
            onClick={() => update.mutate({ status: task.status === "open" ? "done" : "open" })}
            disabled={update.isPending}
          >
            {task.status === "open" ? "Mark as done" : "Mark as not done"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

export default function TasksPage() {
  const app = useApp()
  const me = useMe().data
  const canEdit = me?.role !== "member"
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled: canEdit }).data ?? []
  const { scope } = useScope()
  const [owner, setOwner] = useState("all")
  const [q, setQ] = useState("")
  const [category, setCategory] = useState(ANY)
  const [openId, setOpenId] = useState<string | null>(null)
  const { data } = useQuery({
    queryKey: ["tasks", scope, owner, q, category],
    queryFn: () =>
      api.tasks({
        ...scope,
        owner: owner === "all" ? undefined : owner,
        q,
        category: category === ANY ? undefined : category,
      }),
  })
  const chips: [string, string][] = [
    ["all", "Everyone"],
    ...people.filter((p) => p.role !== "admin").map((p): [string, string] => [p.id, p.name.split(" ")[0]]),
    ["external", "External"],
    [NEEDS_OWNER, `Needs ${app.owner_name}`],
  ]
  const open = data?.find((t) => t.id === openId)

  return (
    <>
      <PageHead title="Tasks" lede="Every action from every meeting, grouped by when it’s due." />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Input
          type="search"
          placeholder="Search tasks"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="max-w-xs bg-card"
          aria-label="Search tasks"
        />
        {canEdit && app.categories.length ? (
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label="Category" className="w-48 bg-card">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>Every category</SelectItem>
              {app.categories.map((c) => (
                <SelectItem key={c.id} value={c.name}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        {canEdit ? (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Owner">
            {chips.map(([value, label]) => (
              <button
                key={value}
                aria-pressed={owner === value}
                onClick={() => setOwner(value)}
                className={cn(
                  "rounded-full border px-3.5 py-1.5 text-sm",
                  owner === value
                    ? "border-foreground bg-foreground text-background"
                    : "bg-card hover:border-foreground/40",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {!data ? (
        <Loading />
      ) : data.length ? (
        <div className="grid max-w-4xl gap-5">
          {BUCKETS.map(([bucket, label]) => {
            const rows = data.filter((t) => t.bucket === bucket)
            if (!rows.length) return null
            const body = (
              <>
                {rows.map((t) => (
                  <div
                    key={t.id}
                    className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-start gap-4 border-t px-5 py-4"
                  >
                    <Tick task={t} />
                    <button className="grid gap-1.5 text-left" onClick={() => setOpenId(t.id)}>
                      <b
                        className={cn(
                          "font-normal text-foreground hover:underline",
                          t.status !== "open" && "text-muted-foreground line-through",
                        )}
                      >
                        {t.description}
                      </b>
                      <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">
                        <span
                          className={cn(!t.owner && !t.owner_name && "text-attention-foreground dark:text-attention")}
                        >
                          {ownerLabel(t, app.owner_name)}
                        </span>
                        <HotelTags properties={t.meeting.properties} />
                        <span>{t.meeting.title}</span>
                      </span>
                    </button>
                    <span
                      className={cn(
                        "tnum pt-0.5 text-sm whitespace-nowrap text-foreground",
                        bucket === "late" && "font-medium text-destructive",
                      )}
                    >
                      {t.due_date ? day(t.due_date) : "No date"}
                    </span>
                  </div>
                ))}
              </>
            )
            const head = (
              <div className="flex items-baseline gap-2 px-5 py-4">
                <h3 className={cn("text-xl", bucket === "late" && "text-destructive")}>{label}</h3>
                <span className="tnum text-sm text-muted-foreground">{rows.length}</span>
              </div>
            )
            return bucket === "done" ? (
              <details key={bucket} className={surface}>
                <summary className="cursor-pointer list-none">{head}</summary>
                {body}
              </details>
            ) : (
              <div key={bucket} className={surface}>
                {head}
                {body}
              </div>
            )
          })}
        </div>
      ) : (
        <Empty>No tasks match.</Empty>
      )}
      {open ? (
        <Drawer
          key={open.id + open.due_date + open.status}
          task={open}
          canEdit={canEdit}
          onClose={() => setOpenId(null)}
        />
      ) : null}
    </>
  )
}

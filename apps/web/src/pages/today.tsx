import { useQuery } from "@tanstack/react-query"
import { AlertTriangle } from "lucide-react"
import { Link } from "react-router-dom"

import { Empty, Loading, PageHead, SectionTitle, surface } from "@/components/page"
import { QuestionCard } from "@/components/question-card"
import { HotelTags, MeetingStatus, Status } from "@/components/tags"
import { useApp } from "@/hooks/use-app"
import { useScope } from "@/hooks/use-scope"
import { api } from "@/lib/api"
import { day, greeting, longDay, plural, time } from "@/lib/format"
import { cn } from "@/lib/utils"

function Stat({
  to,
  value,
  label,
  note,
  hot,
}: {
  to: string
  value: number
  label: string
  note: string
  hot?: boolean
}) {
  return (
    <Link
      to={to}
      className={cn(
        surface,
        "grid content-start gap-1 p-5 transition hover:-translate-y-0.5 hover:border-primary",
        hot && "border-transparent bg-attention-subtle",
      )}
    >
      <b className="font-display tnum mb-2 text-4xl leading-none font-normal text-foreground">{value}</b>
      <span className="font-medium text-foreground">{label}</span>
      <small className="hidden text-sm text-muted-foreground sm:block">{note}</small>
    </Link>
  )
}

function ImpactTeaser() {
  const { property } = useScope()
  const { data } = useQuery({
    queryKey: ["impact", property, "8"],
    queryFn: () => api.impact({ property, weeks: "8" }),
  })
  if (!data || data.followed_up_rate === null) return null
  return (
    <Link
      to="/impact"
      className={cn(surface, "mb-8 flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 hover:border-primary")}
    >
      <span className="text-3xl font-semibold tracking-tight text-foreground">{data.followed_up_rate}%</span>
      <span className="text-foreground">
        of meetings followed up within {data.targets.followup_within_hours} hours over the last 8 weeks.
      </span>
      <span className="ml-auto text-sm underline underline-offset-2">See the impact</span>
    </Link>
  )
}

export default function TodayPage() {
  const { owner_name } = useApp()
  const { scope, property } = useScope()
  const { data } = useQuery({ queryKey: ["today", scope], queryFn: () => api.today(scope) })
  if (!data) return <Loading />

  const isReviewer = data.viewer.role !== "member"
  const followed = data.meetings.filter((m) => m.status === "done" || m.status === "partial").length
  const where = property ? ` at ${property}` : ""

  return (
    <>
      <PageHead
        eyebrow={longDay(data.date)}
        title={`${greeting()}, ${data.viewer.name}.`}
        lede={
          isReviewer
            ? `${plural(data.meetings.length, "call")} today${where}. ${followed} followed up, and nothing has gone out without your approval.`
            : `Your actions from ${owner_name}’s meetings. They reach you in Slack once approved.`
        }
      />

      {isReviewer ? (
        <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
          <Stat
            to="/"
            value={data.counts.questions}
            label="Questions for you"
            note={data.counts.questions ? "Answer right here" : "All answered"}
            hot
          />
          <Stat to="/emails" value={data.counts.emails} label="Emails to review" note="Waiting in your Gmail drafts" />
          <Stat
            to="/slack"
            value={data.counts.slack}
            label="Slack drafts to approve"
            note="For the team and channels"
          />
          <Stat
            to="/tasks"
            value={data.counts.tasks_open}
            label="Open tasks for you"
            note={data.counts.tasks_overdue ? `${data.counts.tasks_overdue} overdue` : "None overdue"}
          />
        </div>
      ) : (
        <div className="mb-8 grid grid-cols-2 gap-3 md:max-w-md">
          <Stat
            to="/tasks"
            value={data.counts.tasks_open}
            label="Open tasks"
            note={data.counts.tasks_overdue ? `${data.counts.tasks_overdue} overdue` : "None overdue"}
          />
        </div>
      )}

      {isReviewer ? <ImpactTeaser /> : null}

      {data.problems.length ? (
        <div className={cn(surface, "mb-8 flex gap-3 border-destructive/30 bg-danger-subtle p-4")}>
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
          <div className="space-y-1 text-sm">
            <p className="font-medium text-foreground">Some meetings need a look</p>
            {data.problems.map((m) => (
              <p key={m.id}>
                <Link to={`/meetings/${m.id}`} className="underline underline-offset-2">
                  {m.title}
                </Link>{" "}
                <span className="text-muted-foreground">
                  ·{" "}
                  {m.status === "failed"
                    ? "couldn’t be processed"
                    : m.status === "waiting"
                      ? "Claude hasn’t answered for hours: check the Claude Code routine is running"
                      : "some drafts failed and will retry"}
                </span>
              </p>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid items-start gap-8 lg:grid-cols-[7fr_5fr]">
        {isReviewer ? (
          <section>
            <SectionTitle title="Today’s calls">
              <span className="text-sm text-muted-foreground">Checked every few minutes</span>
            </SectionTitle>
            <ul className={cn(surface, "divide-y")}>
              {data.meetings.length ? (
                data.meetings.map((m) => (
                  <li key={m.id}>
                    <Link
                      to={`/meetings/${m.id}`}
                      className="grid grid-cols-[3.5rem_1fr] items-baseline gap-x-4 gap-y-1 px-5 py-4 hover:bg-background sm:grid-cols-[3.5rem_1fr_auto]"
                    >
                      <time className="tnum font-medium text-foreground">{time(m.started_at)}</time>
                      <div className="grid gap-1.5">
                        <b className="font-medium text-foreground">{m.title}</b>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted-foreground">
                          <HotelTags properties={m.properties} />
                          <span>{plural(m.attendee_count, "person", "people")}</span>
                          {m.action_count ? <span>{plural(m.action_count, "action")}</span> : null}
                        </div>
                      </div>
                      <span className="col-start-2 sm:col-start-auto">
                        <MeetingStatus status={m.status} />
                      </span>
                    </Link>
                  </li>
                ))
              ) : (
                <li className="px-5 py-4 text-muted-foreground">No calls today{where} yet.</li>
              )}
            </ul>
          </section>
        ) : null}

        <div className="grid gap-8">
          {isReviewer ? (
            <section id="questions">
              <SectionTitle title="Needs your answer">
                {data.questions.length ? (
                  <span className="text-sm text-muted-foreground">Answers update the drafts</span>
                ) : null}
              </SectionTitle>
              <div className="overflow-hidden rounded-xl bg-attention-subtle">
                {data.questions.length ? (
                  data.questions.map((q) => <QuestionCard key={q.id} question={q} />)
                ) : (
                  <p className="px-5 py-4 text-attention-foreground dark:text-attention">
                    All caught up{where}. Nothing needs your answer.
                  </p>
                )}
              </div>
            </section>
          ) : null}

          <section>
            <SectionTitle title="Your next tasks">
              <Link to="/tasks" className="text-sm underline underline-offset-2">
                All tasks
              </Link>
            </SectionTitle>
            {data.next_tasks.length ? (
              <ul className={cn(surface, "divide-y")}>
                {data.next_tasks.map((t) => (
                  <li key={t.id} className="grid grid-cols-[4.5rem_1fr_auto] items-baseline gap-4 px-5 py-4">
                    <time className="tnum text-sm font-medium text-foreground">
                      {t.due_date ? day(t.due_date).replace(/^\w+ /, "") : "—"}
                    </time>
                    <div className="grid gap-1.5">
                      <span className="text-foreground">{t.description}</span>
                      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                        <HotelTags properties={t.meeting.properties} />
                        <span>{t.meeting.title}</span>
                      </div>
                    </div>
                    {t.bucket === "late" ? <Status tone="late">Overdue</Status> : <span />}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>Nothing due this week.</Empty>
            )}
          </section>
        </div>
      </div>
    </>
  )
}

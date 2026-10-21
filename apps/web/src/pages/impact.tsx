import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  CalendarCheck,
  CheckCircle2,
  CircleAlert,
  Clock,
  ListChecks,
  Mail,
  MessageCircleQuestion,
  MessageSquare,
  type LucideIcon,
} from "lucide-react"

import { RowBars, StackedBar, type Part } from "@/components/charts/bars"
import { Columns } from "@/components/charts/columns"
import { RateLine } from "@/components/charts/rate-line"
import { Empty, Loading, PageHead, SectionTitle, surface } from "@/components/page"
import { HotelTag } from "@/components/tags"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useApp } from "@/hooks/use-app"
import { useScope } from "@/hooks/use-scope"
import { api, type Impact } from "@/lib/api"
import { day, every, localDate, minutes as minutesText, plural, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const PERIODS: [string, string][] = [
  ["4", "4 weeks"],
  ["8", "8 weeks"],
  ["12", "12 weeks"],
  ["26", "6 months"],
]

const STATES = {
  on_time: ["Done on time", "var(--state-on-time)"],
  late: ["Done late", "var(--state-late)"],
  open: ["Open, not yet due", "var(--state-open)"],
  overdue: ["Overdue", "var(--state-overdue)"],
} as const

function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—"
  if (minutes < 60) return `${Math.round(minutes)} min`
  if (minutes < 48 * 60) {
    const h = Math.floor(minutes / 60)
    const m = Math.round(minutes % 60)
    return m ? `${h} h ${m} min` : `${h} h`
  }
  return `${(minutes / 1440).toFixed(1)} days`
}

function rate(n: number, d: number) {
  return d ? Math.round((100 * n) / d) : null
}

function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className={cn(surface, "grid content-start gap-2 p-5")}>
      <span className="text-sm font-medium text-muted-foreground">{label}</span>
      <span className="text-3xl font-semibold tracking-tight text-foreground">{value}</span>
      <span className="text-sm text-muted-foreground">{sub}</span>
    </div>
  )
}

/** One thing the app did: the count leads, the icon and words say what it is. */
function Work({ icon: Icon, value, label, sub }: { icon: LucideIcon; value: string; label: string; sub: string }) {
  return (
    <div className={cn(surface, "grid content-start gap-1 p-4 md:p-5")}>
      <span className="mb-2 grid size-9 place-items-center rounded-lg bg-bide-subtle text-bide">
        <Icon className="size-[18px]" aria-hidden />
      </span>
      <span className="font-display tnum text-3xl leading-none text-foreground">{value}</span>
      <span className="text-sm font-medium text-foreground">{label}</span>
      <span className="text-xs text-muted-foreground">{sub}</span>
    </div>
  )
}

/** A health line: what's measured, its value, and whether it's where it should be (icon and words, not colour). */
function Health({ label, value, note, ok }: { label: string; value: string; note: string; ok: boolean | null }) {
  return (
    <li className="grid grid-cols-[1.25rem_1fr_auto] items-start gap-x-3 gap-y-0.5 border-t py-3 first:border-t-0 first:pt-0">
      {ok === null ? (
        <span aria-hidden className="mt-1.5 size-2 justify-self-center rounded-full bg-muted-foreground" />
      ) : ok ? (
        <CheckCircle2 className="mt-0.5 size-5 text-ok" aria-label="On track" />
      ) : (
        <CircleAlert className="mt-0.5 size-5 text-attention" aria-label="Needs a look" />
      )}
      <span className="text-foreground">{label}</span>
      <b className="tnum text-right font-semibold text-foreground">{value}</b>
      <span className="col-start-2 col-end-4 text-sm text-muted-foreground">{note}</span>
    </li>
  )
}

function Performance({ data, children }: { data: Impact; children: React.ReactNode }) {
  const sys = data.system
  const runRate = rate(sys.runs_ok, sys.runs)
  const readRate = rate(sys.meetings_read, sys.meetings_read + sys.meetings_failed)
  const unedited = rate(data.drafts.unedited, data.drafts.acted)
  const ownersRight = data.drafts.actions ? 100 - (rate(data.drafts.reassigned, data.drafts.actions) ?? 0) : null
  const fast = data.minutes_to_drafts
  return (
    <section>
      <SectionTitle title="How the app is performing">
        <span className="text-sm text-muted-foreground">This period</span>
      </SectionTitle>
      <div className="grid items-start gap-4 lg:grid-cols-[5fr_6fr]">
        <ul className={cn(surface, "grid content-start p-5")}>
          <Health
            label="Runs completed"
            value={runRate === null ? "—" : `${runRate}%`}
            note={
              sys.runs
                ? `${sys.runs_ok} of ${plural(sys.runs, "run")}` +
                  (sys.last_failed_run_at
                    ? ` · last problem ${day(localDate(sys.last_failed_run_at))} ${time(sys.last_failed_run_at)}`
                    : " · no problems")
                : "No runs in this period"
            }
            ok={runRate === null ? null : runRate >= 95}
          />
          <Health
            label="Meetings read without a problem"
            value={readRate === null ? "—" : `${readRate}%`}
            note={`${sys.meetings_read} read, ${sys.meetings_failed} couldn’t be, ${sys.meetings_skipped} skipped by the rules`}
            ok={readRate === null ? null : readRate >= 95}
          />
          <Health
            label="Drafts ready after a meeting ends"
            value={duration(fast)}
            note={`On average. Target: under ${minutesText(data.targets.target_minutes_to_drafts)}`}
            ok={fast === null ? null : fast <= data.targets.target_minutes_to_drafts}
          />
          <Health
            label={`Drafts ${data.owner_name} sent as written`}
            value={unedited === null ? "—" : `${unedited}%`}
            note={`How often Claude’s wording was right first time. Target: ${data.targets.target_unedited_rate}% or more`}
            ok={unedited === null ? null : unedited >= data.targets.target_unedited_rate}
          />
          <Health
            label="Tasks given to the right person"
            value={ownersRight === null ? "—" : `${ownersRight}%`}
            note={`${data.drafts.reassigned} of ${plural(data.drafts.actions, "task")} moved to someone else by ${data.owner_name}`}
            ok={ownersRight === null ? null : 100 - ownersRight <= data.targets.target_reassigned_rate}
          />
          <Health
            label={`Days ${data.owner_name} used the app this week`}
            value={String(data.david_active_days)}
            note={`Target: ${data.targets.target_active_days} or more working days`}
            ok={data.david_active_days >= data.targets.target_active_days}
          />
          <Health
            label="Claude"
            value={sys.mode === "routine" ? "Claude Code" : "Claude API"}
            note={
              sys.tokens_per_meeting
                ? `About ${sys.tokens_per_meeting.toLocaleString("en-GB")} tokens per meeting`
                : sys.mode === "routine"
                  ? "On Bide’s Claude plan: no per-use bill"
                  : "No usage recorded yet"
            }
            ok={null}
          />
        </ul>
        <div className="grid gap-4">
          <section className={cn(surface, "grid content-start gap-4 p-5")}>
            <div>
              <h3 className="text-xl">Meetings the app handled, by week</h3>
              <p className="text-sm text-muted-foreground">
                Read and followed up, couldn’t be read, or skipped by the rules
              </p>
            </div>
            <Columns
              label="Meetings handled by week"
              columns={sys.weeks.map((w) => ({
                label: day(w.week_start).replace(/^\w+ /, ""),
                parts: [
                  { label: "Read", value: w.read, color: "var(--chart-1)" },
                  { label: "Couldn’t be read", value: w.failed, color: "var(--state-overdue)" },
                  { label: "Skipped", value: w.skipped, color: "var(--chart-5)" },
                ],
              }))}
            />
          </section>
          {children}
        </div>
      </div>
    </section>
  )
}

function definitions(owner: string, hours: number, gmailMinutes: number): [string, string][] {
  return [
    [
      `Followed up within ${hours} hours`,
      `${owner} approved a Slack message, or the follow-up email left their Gmail drafts, within ${hours} hours of the meeting ending. Only meetings that produced drafts count, plus any the app couldn’t process. Skipped meetings and internal calls with nothing to send are left out.`,
    ],
    [
      "Time to follow-up",
      `From the end of the meeting to ${owner}’s first approval, averaged over meetings acted on. For emails the app checks Gmail ${every(gmailMinutes)}, so this can read up to ${minutesText(gmailMinutes)} late.`,
    ],
    [
      "Emails",
      "The app only has permission to manage drafts, so it can see a draft leave Gmail but not whether it was sent or deleted; it counts as acted on either way. Edits made inside Gmail aren’t seen.",
    ],
    [
      "Actions captured",
      "Tasks taken from the notes, dismissed ones left out. “On time” means ticked done on or before the due date; a task with no date counts as on time.",
    ],
    [
      "Different owner",
      `Tasks Claude gave to someone that ${owner} then moved to someone else: how often Claude got the owner wrong.`,
    ],
    [
      "Before launch",
      "The app has no data from before it existed. Admin can enter the earlier follow-up rate and time (Admin → Claude, email and schedule) to show the comparison.",
    ],
    ["Targets", "Set in Admin → Claude, email and schedule; they start at the PRD’s success measures."],
    ["Time saved", "An estimate, not a measurement: meetings the app handled, times the minutes set above."],
    [
      "Runs completed",
      "The app checks Drive every few minutes. A run that stopped on a problem (Google or Slack disconnected, Claude unreachable) counts against this; the next run carries on where it stopped.",
    ],
    [
      "Meetings read",
      "Notes Claude read and turned into drafts, tasks and questions. “Couldn’t be read” means it gave up after its retries; “skipped” means a skip rule in Admin left the meeting out.",
    ],
    [
      "Right person",
      `Tasks Claude gave an owner that ${owner} didn’t move to someone else. Tasks Claude couldn’t place go to ${owner} as questions instead.`,
    ],
  ]
}

export default function ImpactPage() {
  const app = useApp()
  const { property } = useScope()
  const [weeks, setWeeks] = useState("8")
  const [minutes, setMinutes] = useState<number | null>(null)
  const { data, isFetching } = useQuery({
    queryKey: ["impact", property, weeks],
    queryFn: () => api.impact({ property, weeks }),
    placeholderData: (previous) => previous,
  })
  if (!data) return <Loading />

  const perMeeting = minutes ?? data.minutes_saved_per_meeting
  const saved = Math.round((data.meetings_handled * perMeeting) / 60)
  const fullWeeks = data.weeks.filter((w) => !w.in_progress).length || 1
  const actions: Part[] = (Object.keys(STATES) as (keyof typeof STATES)[]).map((k) => ({
    label: STATES[k][0],
    value: data.actions[k],
    color: STATES[k][1],
  }))
  const captured = actions.reduce((s, p) => s + p.value, 0)
  const openTotal = data.owners.reduce((s, o) => s + o.open + o.overdue, 0)
  const overdueTotal = data.owners.reduce((s, o) => s + o.overdue, 0)
  const scope = property ?? "All properties"

  return (
    <>
      <PageHead
        eyebrow={`Since ${day(data.since)} · ${PERIODS.find((p) => p[0] === weeks)?.[1]}`}
        title="Impact"
        lede="How much the app helps: the work it takes off your plate, whether meetings turn into follow-ups and the team follows through, and how well it runs. Measured from the app’s own records."
      />

      <div className="mb-6 flex flex-wrap items-center gap-2" role="group" aria-label="Period">
        {PERIODS.map(([value, label]) => (
          <button
            key={value}
            aria-pressed={weeks === value}
            onClick={() => setWeeks(value)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-sm",
              weeks === value
                ? "border-foreground bg-foreground text-background"
                : "bg-card hover:border-foreground/40",
            )}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-sm text-muted-foreground">
          Showing <b className="font-medium text-foreground">{scope}</b> · change it from the property menu
        </span>
      </div>

      {data.meetings === 0 ? (
        <Empty>No meetings to measure in this period yet. The numbers fill in as meetings are followed up.</Empty>
      ) : (
        <div className={cn("grid grid-cols-1 gap-6 transition-opacity", isFetching && "opacity-60")}>
          <section aria-label="What the app did">
            <SectionTitle title="What the app did for you" />
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:gap-4 xl:grid-cols-6">
              <Work
                icon={CalendarCheck}
                value={String(data.system.meetings_read)}
                label="Meetings read"
                sub="Notes turned into follow-ups"
              />
              <Work icon={ListChecks} value={String(captured)} label="Actions captured" sub="Each with an owner" />
              <Work
                icon={Mail}
                value={String(data.system.emails_drafted)}
                label="Emails drafted"
                sub="Waiting in Gmail, never sent"
              />
              <Work
                icon={MessageSquare}
                value={String(data.system.slack_posted)}
                label="Slack messages sent"
                sub={`of ${data.system.slack_drafted} drafted, after approval`}
              />
              <Work
                icon={MessageCircleQuestion}
                value={String(data.system.questions_answered)}
                label="Questions settled"
                sub={`of ${data.system.questions_asked} asked about owners and dates`}
              />
              <Work
                icon={Clock}
                value={`${saved} h`}
                label="Time saved"
                sub={`About ${Math.round(saved / fullWeeks)} h a week (estimate)`}
              />
            </div>
          </section>
          <section className={cn(surface, "grid grid-cols-1 items-center gap-6 p-5 md:p-6 lg:grid-cols-[4fr_7fr]")}>
            <div>
              <span className="text-sm font-medium text-muted-foreground">
                Meetings followed up within {data.targets.followup_within_hours} hours
              </span>
              <div className="my-2 text-6xl font-semibold tracking-tight text-foreground md:text-7xl">
                {data.followed_up_rate ?? 0}%
              </div>
              <p className="max-w-[34ch] text-lg text-foreground">
                {data.followed_up} of {plural(data.meetings, "meeting")} that needed a follow-up got one within{" "}
                {data.targets.followup_within_hours} hours.
              </p>
              {data.baseline_followup_rate !== null ? (
                <span
                  className={cn(
                    "mt-3 inline-flex rounded-full px-2.5 py-1 text-sm font-medium",
                    (data.followed_up_rate ?? 0) >= data.baseline_followup_rate
                      ? "bg-ok-subtle text-ok-foreground"
                      : "bg-danger-subtle text-destructive",
                  )}
                >
                  {(data.followed_up_rate ?? 0) >= data.baseline_followup_rate ? "▲" : "▼"}{" "}
                  {Math.abs((data.followed_up_rate ?? 0) - data.baseline_followup_rate)} points vs{" "}
                  {data.baseline_followup_rate}% before launch
                </span>
              ) : null}
            </div>
            <div className="min-w-0">
              <RateLine
                label={`Weekly share of meetings followed up within ${data.targets.followup_within_hours} hours`}
                points={data.weeks.map((w) => ({
                  week: w.week_start,
                  rate: w.rate,
                  inProgress: w.in_progress,
                  detail: `${w.followed_up} of ${plural(w.meetings, "meeting")}`,
                }))}
              />
              <details className="mt-2 text-sm">
                <summary className="inline-block cursor-pointer underline underline-offset-2">
                  Show weekly numbers
                </summary>
                <div className="mt-3 overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Week of</TableHead>
                        <TableHead className="text-right">Meetings</TableHead>
                        <TableHead className="text-right">Followed up in 24 h</TableHead>
                        <TableHead className="text-right">Rate</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.weeks.map((w) => (
                        <TableRow key={w.week_start}>
                          <TableCell>
                            {day(w.week_start)}
                            {w.in_progress ? <span className="text-muted-foreground"> · so far</span> : null}
                          </TableCell>
                          <TableCell className="tnum text-right">{w.meetings}</TableCell>
                          <TableCell className="tnum text-right">{w.followed_up}</TableCell>
                          <TableCell className="tnum text-right">{w.rate === null ? "—" : `${w.rate}%`}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </details>
            </div>
          </section>

          <div className="grid grid-cols-2 gap-3 md:gap-4 lg:grid-cols-4">
            <Kpi
              label="Time to follow-up"
              value={duration(data.minutes_to_follow_up)}
              sub={
                data.baseline_followup_days !== null
                  ? `From meeting end to ${data.owner_name} acting · was ${data.baseline_followup_days} days`
                  : `From meeting end to ${data.owner_name} acting`
              }
            />
            <Kpi
              label="Actions done on time"
              value={data.actions.on_time_rate === null ? "—" : `${data.actions.on_time_rate}%`}
              sub={`${data.actions.on_time} on time, ${data.actions.late} late`}
            />
            <Kpi
              label={`Drafts ${data.owner_name} acted on`}
              value={String(data.drafts.acted)}
              sub={`${data.drafts.unedited} without changing a word`}
            />
            <Kpi label="Overdue now" value={String(overdueTotal)} sub={`of ${plural(openTotal, "open action")}`} />
          </div>

          <div className="grid items-start gap-4 lg:grid-cols-2">
            <section className={cn(surface, "grid content-start gap-4 p-5")}>
              <div>
                <h3 className="text-xl">Where the actions are now</h3>
                <p className="text-sm text-muted-foreground">All {captured} actions from meetings in this period</p>
              </div>
              <StackedBar parts={actions} label="Actions by state" />
            </section>
            <section className={cn(surface, "grid content-start gap-4 p-5")}>
              <div>
                <h3 className="text-xl">Open actions by owner</h3>
                <p className="text-sm text-muted-foreground">
                  {openTotal} open, {overdueTotal} of them overdue
                </p>
              </div>
              {data.owners.length ? (
                <RowBars
                  keyParts={[
                    { label: "Open, not yet due", color: "var(--state-open)" },
                    { label: "Overdue", color: "var(--state-overdue)" },
                  ]}
                  rows={data.owners.map((o) => ({
                    label: o.name,
                    parts: [
                      { label: "Open, not yet due", value: o.open, color: "var(--state-open)" },
                      { label: "Overdue", value: o.overdue, color: "var(--state-overdue)" },
                    ],
                  }))}
                />
              ) : (
                <p className="text-muted-foreground">Nothing open. Everyone is clear.</p>
              )}
            </section>
          </div>

          <Performance data={data}>
            <section className={cn(surface, "grid content-start gap-4 p-5")}>
              <div>
                <span className="eyebrow text-muted-foreground">Time saved · estimate</span>
                <div className="mt-1 text-5xl font-semibold tracking-tight text-foreground">{saved} hours</div>
                <p className="tnum mt-2 text-sm text-muted-foreground">
                  {plural(data.meetings_handled, "meeting")} × {perMeeting} minutes = {saved} hours, about{" "}
                  {Math.round(saved / fullWeeks)} hours a week.
                </p>
              </div>
              <div className="grid gap-2">
                <label htmlFor="minutes" className="flex justify-between text-sm text-muted-foreground">
                  <span>Minutes saved per meeting</span>
                  <b className="font-semibold text-foreground">{perMeeting} min</b>
                </label>
                <input
                  id="minutes"
                  type="range"
                  min={5}
                  max={45}
                  step={5}
                  value={perMeeting}
                  onChange={(e) => setMinutes(Number(e.target.value))}
                  className="w-full accent-[var(--chart-1)]"
                />
                <p className="text-sm text-muted-foreground">
                  The time it would take to write the recap, email the attendees, message the team and update the task
                  list by hand.
                </p>
              </div>
            </section>
          </Performance>

          {data.hotels.length ? (
            <section>
              <SectionTitle title="By property">
                <span className="text-sm text-muted-foreground">This period</span>
              </SectionTitle>
              <div className={cn(surface, "overflow-x-auto")}>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Property</TableHead>
                      <TableHead className="text-right">Meetings</TableHead>
                      <TableHead className="text-right">Followed up in 24 h</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                      <TableHead className="text-right">Done on time</TableHead>
                      <TableHead className="text-right">Overdue now</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.hotels.map((h) => (
                      <TableRow key={h.name}>
                        <TableCell>
                          <HotelTag name={h.name} />
                        </TableCell>
                        <TableCell className="tnum text-right">{h.meetings}</TableCell>
                        <TableCell className="tnum text-right">
                          {h.followed_up_rate === null ? "—" : `${h.followed_up_rate}%`}
                        </TableCell>
                        <TableCell className="tnum text-right">{h.actions}</TableCell>
                        <TableCell className="tnum text-right">
                          {h.on_time_rate === null ? "—" : `${h.on_time_rate}%`}
                        </TableCell>
                        <TableCell className="tnum text-right">{h.overdue}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </section>
          ) : null}
        </div>
      )}

      <section className="mt-10">
        <SectionTitle title="How these numbers are measured" />
        <dl className={cn(surface, "grid gap-4 p-5")}>
          {definitions(
            data?.owner_name ?? "the owner",
            data?.targets.followup_within_hours ?? 24,
            app.pipeline.gmail_sync_minutes,
          ).map(([term, text]) => (
            <div
              key={term}
              className="grid gap-1 border-t pt-4 first:border-t-0 first:pt-0 sm:grid-cols-[14rem_1fr] sm:gap-4"
            >
              <dt className="font-medium text-foreground">{term}</dt>
              <dd className="max-w-prose text-muted-foreground">{text}</dd>
            </div>
          ))}
        </dl>
      </section>
    </>
  )
}

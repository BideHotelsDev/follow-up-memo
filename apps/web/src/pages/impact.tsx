import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, CircleAlert } from "lucide-react"

import { RowBars, StackedBar, type Part } from "@/components/charts/bars"
import { RateLine } from "@/components/charts/rate-line"
import { Empty, Loading, PageHead, SectionTitle, surface } from "@/components/page"
import { HotelTag } from "@/components/tags"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useScope } from "@/hooks/use-scope"
import { api, type Impact } from "@/lib/api"
import { day, plural } from "@/lib/format"
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

/** The PRD's success measures, each against its target, with an icon and words (never colour alone). */
function Targets({ data }: { data: Impact }) {
  const unedited = rate(data.drafts.unedited, data.drafts.acted)
  const reassigned = rate(data.drafts.reassigned, data.drafts.actions)
  const rows: [string, string, boolean | null, string][] = [
    [
      "Drafts ready after a meeting ends",
      duration(data.minutes_to_drafts),
      data.minutes_to_drafts === null ? null : data.minutes_to_drafts <= 30,
      "Target: under 30 minutes",
    ],
    [
      "Drafts approved without edits",
      unedited === null ? "—" : `${unedited}%`,
      unedited === null ? null : unedited >= 70,
      `Target: 70% or more · ${data.drafts.unedited} of ${data.drafts.acted}`,
    ],
    [
      "Tasks David had to give a different owner",
      reassigned === null ? "—" : `${reassigned}%`,
      reassigned === null ? null : reassigned < 5,
      `Target: under 5% · ${data.drafts.reassigned} of ${data.drafts.actions}`,
    ],
    [
      "Days David used the app this week",
      String(data.david_active_days),
      data.david_active_days >= 4,
      "Target: 4 or more working days",
    ],
  ]
  return (
    <ul className="divide-y">
      {rows.map(([label, value, met, note]) => (
        <li key={label} className="grid grid-cols-[1.25rem_1fr_auto] items-start gap-3 py-3 first:pt-0 last:pb-0">
          {met === null ? (
            <span aria-hidden className="mt-1 size-3 rounded-full border border-muted-foreground" />
          ) : met ? (
            <CheckCircle2 className="mt-0.5 size-5 text-ok" aria-label="On target" />
          ) : (
            <CircleAlert className="mt-0.5 size-5 text-attention" aria-label="Below target" />
          )}
          <div className="grid gap-0.5">
            <span className="text-foreground">{label}</span>
            <span className="text-sm text-muted-foreground">
              {met === null ? "Not enough data yet · " : ""}
              {note}
            </span>
          </div>
          <span className="tnum font-semibold text-foreground">{value}</span>
        </li>
      ))}
    </ul>
  )
}

export default function ImpactPage() {
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
        lede="Whether meetings turn into follow-ups, how fast, and whether the team follows through. Measured from the app’s own records."
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
          <section className={cn(surface, "grid grid-cols-1 items-center gap-6 p-5 md:p-6 lg:grid-cols-[4fr_7fr]")}>
            <div>
              <span className="text-sm font-medium text-muted-foreground">Meetings followed up within 24 hours</span>
              <div className="my-2 text-6xl font-semibold tracking-tight text-foreground md:text-7xl">
                {data.followed_up_rate ?? 0}%
              </div>
              <p className="max-w-[34ch] text-lg text-foreground">
                {data.followed_up} of {plural(data.meetings, "meeting")} that needed a follow-up got one within a day.
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
                label="Weekly share of meetings followed up within 24 hours"
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
                  ? `From meeting end to David acting · was ${data.baseline_followup_days} days`
                  : "From meeting end to David acting"
              }
            />
            <Kpi
              label="Actions captured"
              value={String(captured)}
              sub={
                data.actions.on_time_rate !== null
                  ? `${data.actions.on_time_rate}% of the done ones on time`
                  : "None done yet"
              }
            />
            <Kpi
              label="Drafts David acted on"
              value={String(data.drafts.acted)}
              sub={`${data.drafts.unedited} without changing a word`}
            />
            <Kpi
              label="Time saved (estimate)"
              value={`${saved} h`}
              sub={`About ${Math.round(saved / fullWeeks)} h a week`}
            />
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

          <div className="grid items-start gap-4 lg:grid-cols-2">
            <section className={cn(surface, "grid content-start gap-4 p-5")}>
              <h3 className="text-xl">Against the targets</h3>
              <Targets data={data} />
            </section>
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
          </div>

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
          {[
            [
              "Followed up within 24 hours",
              "David approved a Slack message, or the follow-up email left his Gmail drafts, within 24 hours of the meeting ending. Only meetings that produced drafts count, plus any the app couldn’t process. Skipped meetings and internal calls with nothing to send are left out.",
            ],
            [
              "Time to follow-up",
              "From the end of the meeting to David’s first approval, averaged over meetings he acted on. For emails the app checks Gmail every 30 minutes, so this can read up to half an hour late.",
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
              "Tasks Claude gave to someone that David then moved to someone else: how often Claude got the owner wrong.",
            ],
            [
              "Before launch",
              "The app has no data from before it existed. Admin can enter the earlier follow-up rate and time (Admin → Email and schedule) to show the comparison.",
            ],
            ["Time saved", "An estimate, not a measurement: meetings the app handled, times the minutes set above."],
          ].map(([term, text]) => (
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

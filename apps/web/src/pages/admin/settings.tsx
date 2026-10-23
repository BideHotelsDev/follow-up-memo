import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api, HttpError, type Settings } from "@/lib/api"
import { cn } from "@/lib/utils"

type Timing = "quiet_minutes" | "lookback_days" | "max_attempts" | "gmail_sync_minutes" | "raw_text_days"

const TIMINGS: { key: Timing; label: string; min: number; max: number; hint: string }[] = [
  {
    key: "quiet_minutes",
    label: "Wait after Gemini’s last edit (minutes)",
    min: 5,
    max: 120,
    hint: "So a note isn’t read while Gemini is still writing it.",
  },
  {
    key: "lookback_days",
    label: "Look for notes from the last (days)",
    min: 1,
    max: 14,
    hint: "Older notes are left alone.",
  },
  {
    key: "max_attempts",
    label: "Tries before a meeting is marked failed",
    min: 1,
    max: 10,
    hint: "Each run tries again until then.",
  },
  {
    key: "gmail_sync_minutes",
    label: "Check Gmail drafts every (minutes)",
    min: 10,
    max: 240,
    hint: "To see which drafts were sent or deleted.",
  },
  {
    key: "raw_text_days",
    label: "Keep the note text for (days)",
    min: 1,
    max: 365,
    hint: "Then it’s deleted; drafts and tasks stay.",
  },
]

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
const HOURS = Array.from({ length: 14 }, (_, i) => i + 5) // 5am to 6pm, as the API allows

function HourSelect({ id, value, onChange }: { id: string; value: number; onChange: (hour: number) => void }) {
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger id={id} className="w-32 bg-card">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {HOURS.map((h) => (
          <SelectItem key={h} value={String(h)}>
            {`${String(h).padStart(2, "0")}:00`}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** Shows what a scheduled message would say today, without sending it. */
function Preview({ label, load }: { label: string; load: () => Promise<{ text: string }> }) {
  const [text, setText] = useState<string | null>(null)
  const show = useMutation({ mutationFn: load, onSuccess: (r) => setText(r.text) })
  return (
    <div className="grid gap-2">
      <Button type="button" variant="outline" className="justify-self-start" onClick={() => show.mutate()}>
        {show.isPending ? "Loading…" : label}
      </Button>
      {text !== null ? (
        <pre className="rounded-md border bg-muted/40 p-3 text-xs whitespace-pre-wrap">{text}</pre>
      ) : null}
    </div>
  )
}

/** "a.com, b.com" ↔ ["a.com", "b.com"] */
const split = (text: string) =>
  text
    .split(/[,\n]/)
    .map((part) => part.trim())
    .filter(Boolean)

function Form({ initial }: { initial: Settings }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(initial)
  const [domains, setDomains] = useState(initial.internal_domains.join(", "))
  const [topics, setTopics] = useState(initial.sensitive_topics.join(", "))
  const save = useMutation({
    mutationFn: () =>
      api.putSettings({
        email_tone: form.email_tone,
        email_signature: form.email_signature,
        extract_instructions: form.extract_instructions,
        email_instructions: form.email_instructions,
        reminders_enabled: form.reminders_enabled,
        reminder_hour: form.reminder_hour,
        undated_nudge_enabled: form.undated_nudge_enabled,
        undated_nudge_weekday: form.undated_nudge_weekday,
        weekly_digest_enabled: form.weekly_digest_enabled,
        digest_weekday: form.digest_weekday,
        digest_hour: form.digest_hour,
        poll_interval_minutes: form.poll_interval_minutes,
        minutes_saved_per_meeting: form.minutes_saved_per_meeting,
        baseline_followup_rate: form.baseline_followup_rate,
        baseline_followup_days: form.baseline_followup_days,
        target_minutes_to_drafts: form.target_minutes_to_drafts,
        target_unedited_rate: form.target_unedited_rate,
        target_reassigned_rate: form.target_reassigned_rate,
        target_active_days: form.target_active_days,
        followup_within_hours: form.followup_within_hours,
        routine_stuck_hours: form.routine_stuck_hours,
        internal_domains: split(domains),
        property_region: form.property_region,
        sensitive_topics: split(topics),
        ...Object.fromEntries(TIMINGS.map(({ key }) => [key, form[key]])),
      }),
    onSuccess: (saved) => {
      setDomains(saved.internal_domains.join(", "))
      setTopics(saved.sensitive_topics.join(", "))
      queryClient.invalidateQueries({ queryKey: ["settings"] })
      queryClient.invalidateQueries({ queryKey: ["app"] })
      toast.success("Saved")
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })

  return (
    <form
      className={cn(surface, "grid max-w-2xl gap-5 p-5")}
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor="tone">Email tone</Label>
        <Textarea
          id="tone"
          rows={3}
          value={form.email_tone}
          onChange={(e) => setForm({ ...form, email_tone: e.target.value })}
        />
        <p className="text-xs text-muted-foreground">Claude writes each follow-up email in this tone.</p>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="signature">Signature</Label>
        <Textarea
          id="signature"
          rows={3}
          value={form.email_signature}
          onChange={(e) => setForm({ ...form, email_signature: e.target.value })}
        />
      </div>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Instructions for Claude</legend>
        <p className="text-sm text-muted-foreground">
          Your own rules, in your own words, one per line. Claude follows them on top of its usual ones, but it still
          never adds anything the notes don’t say.
        </p>
        <div className="grid gap-1.5">
          <Label htmlFor="extract-instructions">When reading meeting notes</Label>
          <Textarea
            id="extract-instructions"
            rows={4}
            maxLength={4000}
            placeholder={
              "Linen and laundry actions are Russell’s unless the notes say otherwise.\nTreat anything about the Glasgow site as sensitive."
            }
            value={form.extract_instructions}
            onChange={(e) => setForm({ ...form, extract_instructions: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            Used when Claude pulls out actions, owners, deadlines, categories and questions.
          </p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="email-instructions">When writing follow-up emails</Label>
          <Textarea
            id="email-instructions"
            rows={4}
            maxLength={4000}
            placeholder={"Never mention our rates or occupancy to OTAs.\nKeep emails to suppliers under 120 words."}
            value={form.email_instructions}
            onChange={(e) => setForm({ ...form, email_instructions: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            Applies to new drafts. To redo one already written, reprocess its meeting.
          </p>
        </div>
      </fieldset>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Reminders and weekly digest</legend>
        <div className="grid gap-2">
          <label className="flex items-center gap-2">
            <Switch
              checked={form.reminders_enabled}
              onCheckedChange={(on) => setForm({ ...form, reminders_enabled: on })}
              aria-label="Send due-date reminders"
            />
            Send due-date reminders
          </label>
          <p className="text-xs text-muted-foreground">
            On weekdays, a Slack message to each person with tasks due that day or overdue. These go to the team without
            your approval, so they start switched off.
          </p>
          <div className="flex items-center gap-2">
            <Label htmlFor="reminder-hour">At</Label>
            <HourSelect
              id="reminder-hour"
              value={form.reminder_hour}
              onChange={(h) => setForm({ ...form, reminder_hour: h })}
            />
          </div>
          <Preview label="Preview my reminder" load={api.reminderPreview} />
        </div>
        <div className="grid gap-2">
          <label className="flex items-center gap-2">
            <Switch
              checked={form.undated_nudge_enabled}
              onCheckedChange={(on) => setForm({ ...form, undated_nudge_enabled: on })}
              aria-label="Send a weekly nudge about tasks with no due date"
            />
            Send a weekly nudge about tasks with no due date
          </label>
          <p className="text-xs text-muted-foreground">
            The daily reminder only covers tasks with a date. Once a week, at the reminder time, each person gets a
            Slack message listing their open tasks that have none, to tick off or give a date.
          </p>
          <div className="flex items-center gap-2">
            <Label htmlFor="nudge-day">Every</Label>
            <Select
              value={String(form.undated_nudge_weekday)}
              onValueChange={(v) => setForm({ ...form, undated_nudge_weekday: Number(v) })}
            >
              <SelectTrigger id="nudge-day" className="w-36 bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WEEKDAYS.slice(0, 5).map((d, i) => (
                  <SelectItem key={d} value={String(i)}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Preview label="Preview my nudge" load={api.undatedPreview} />
        </div>
        <div className="grid gap-2">
          <label className="flex items-center gap-2">
            <Switch
              checked={form.weekly_digest_enabled}
              onCheckedChange={(on) => setForm({ ...form, weekly_digest_enabled: on })}
              aria-label="Send the weekly digest"
            />
            Send the owner a weekly digest
          </label>
          <p className="text-xs text-muted-foreground">
            The past seven days: meetings processed, actions done on time or late, what’s overdue and who has it, and
            what’s still waiting for you.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Label htmlFor="digest-day">Every</Label>
            <Select
              value={String(form.digest_weekday)}
              onValueChange={(v) => setForm({ ...form, digest_weekday: Number(v) })}
            >
              <SelectTrigger id="digest-day" className="w-36 bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WEEKDAYS.map((d, i) => (
                  <SelectItem key={d} value={String(i)}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Label htmlFor="digest-hour">at</Label>
            <HourSelect
              id="digest-hour"
              value={form.digest_hour}
              onChange={(h) => setForm({ ...form, digest_hour: h })}
            />
          </div>
          <Preview label="Preview this week’s digest" load={api.digestPreview} />
        </div>
      </fieldset>
      <div className="grid gap-1.5">
        <Label htmlFor="interval">Check Drive every (minutes)</Label>
        <Input
          id="interval"
          type="number"
          min={5}
          max={60}
          className="w-28"
          value={form.poll_interval_minutes}
          onChange={(e) => setForm({ ...form, poll_interval_minutes: Number(e.target.value) })}
        />
        <p className="text-xs text-muted-foreground">Takes effect within a minute.</p>
      </div>
      <p className="text-sm text-muted-foreground">Slack messages always wait for the owner’s approval.</p>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Bide</legend>
        <div className="grid gap-1.5">
          <Label htmlFor="domains">Bide email domains</Label>
          <Input id="domains" value={domains} onChange={(e) => setDomains(e.target.value)} />
          <p className="text-xs text-muted-foreground">
            Separated by commas. People at these domains count as internal and can sign in once they’re added in People.
            Everyone else gets the follow-up email.
          </p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="region">Where the properties are</Label>
          <Input
            id="region"
            className="max-w-xs"
            value={form.property_region}
            onChange={(e) => setForm({ ...form, property_region: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">Claude is told “Bide runs short-stay properties in …”.</p>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="topics">Sensitive topics</Label>
          <Textarea id="topics" rows={2} value={topics} onChange={(e) => setTopics(e.target.value)} />
          <p className="text-xs text-muted-foreground">
            Separated by commas. Meetings about these get no team messages, and their email is flagged for a careful
            read.
          </p>
        </div>
      </fieldset>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Timings</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          {TIMINGS.map(({ key, label, min, max, hint }) => (
            <div key={key} className="grid content-start gap-1.5">
              <Label htmlFor={key}>{label}</Label>
              <Input
                id={key}
                type="number"
                min={min}
                max={max}
                className="w-28"
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
              />
              <p className="text-xs text-muted-foreground">{hint}</p>
            </div>
          ))}
        </div>
      </fieldset>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Impact page</legend>
        <div className="grid gap-1.5">
          <Label htmlFor="minutes">Minutes a meeting’s follow-up takes by hand</Label>
          <Input
            id="minutes"
            type="number"
            min={1}
            max={240}
            className="w-28"
            value={form.minutes_saved_per_meeting}
            onChange={(e) => setForm({ ...form, minutes_saved_per_meeting: Number(e.target.value) })}
          />
          <p className="text-xs text-muted-foreground">The starting point for the time-saved estimate.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="base-rate">Before launch: % followed up in time</Label>
            <Input
              id="base-rate"
              type="number"
              min={0}
              max={100}
              placeholder="Not set"
              value={form.baseline_followup_rate ?? ""}
              onChange={(e) =>
                setForm({ ...form, baseline_followup_rate: e.target.value === "" ? null : Number(e.target.value) })
              }
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="base-days">Before launch: days to follow up</Label>
            <Input
              id="base-days"
              type="number"
              min={0}
              max={60}
              step={0.5}
              placeholder="Not set"
              value={form.baseline_followup_days ?? ""}
              onChange={(e) =>
                setForm({ ...form, baseline_followup_days: e.target.value === "" ? null : Number(e.target.value) })
              }
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Optional. The app has no data from before it existed; fill these in from the owner’s own estimate to show the
          before-and-after.
        </p>
      </fieldset>
      <fieldset className="grid gap-4 border-t pt-5">
        <legend className="mb-2 font-medium">Targets</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="followup_within_hours">Counts as followed up within (hours)</Label>
            <Input
              id="followup_within_hours"
              type="number"
              min={0}
              className="w-28"
              value={form.followup_within_hours}
              onChange={(e) => setForm({ ...form, followup_within_hours: Number(e.target.value) })}
            />
            <p className="text-xs text-muted-foreground">The window behind the Impact headline.</p>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="target_minutes_to_drafts">Target: drafts ready within (minutes)</Label>
            <Input
              id="target_minutes_to_drafts"
              type="number"
              min={0}
              className="w-28"
              value={form.target_minutes_to_drafts}
              onChange={(e) => setForm({ ...form, target_minutes_to_drafts: Number(e.target.value) })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="target_unedited_rate">Target: drafts approved without edits (%)</Label>
            <Input
              id="target_unedited_rate"
              type="number"
              min={0}
              className="w-28"
              value={form.target_unedited_rate}
              onChange={(e) => setForm({ ...form, target_unedited_rate: Number(e.target.value) })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="target_reassigned_rate">Target: tasks given a different owner, under (%)</Label>
            <Input
              id="target_reassigned_rate"
              type="number"
              min={0}
              className="w-28"
              value={form.target_reassigned_rate}
              onChange={(e) => setForm({ ...form, target_reassigned_rate: Number(e.target.value) })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="target_active_days">Target: days the owner uses the app each week</Label>
            <Input
              id="target_active_days"
              type="number"
              min={0}
              className="w-28"
              value={form.target_active_days}
              onChange={(e) => setForm({ ...form, target_active_days: Number(e.target.value) })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="routine_stuck_hours">Warn when Claude hasn’t answered for (hours)</Label>
            <Input
              id="routine_stuck_hours"
              type="number"
              min={0}
              className="w-28"
              value={form.routine_stuck_hours}
              onChange={(e) => setForm({ ...form, routine_stuck_hours: Number(e.target.value) })}
            />
            <p className="text-xs text-muted-foreground">Routine mode: Today flags meetings waiting this long.</p>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          They start at the PRD’s success measures and show on the Impact page.
        </p>
      </fieldset>
      <div>
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  )
}

export default function SettingsPage() {
  const { data } = useQuery({ queryKey: ["settings"], queryFn: api.settings })
  return data ? <Form initial={data} /> : <Loading />
}

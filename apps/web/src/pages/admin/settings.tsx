import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api, HttpError, type Settings } from "@/lib/api"
import { cn } from "@/lib/utils"

function Form({ initial }: { initial: Settings }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(initial)
  const save = useMutation({
    mutationFn: () =>
      api.putSettings({
        email_tone: form.email_tone,
        email_signature: form.email_signature,
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
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] })
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
        <p className="text-xs text-muted-foreground">Takes effect when the worker restarts.</p>
      </div>
      <p className="text-sm text-muted-foreground">Slack messages always wait for the owner’s approval.</p>
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

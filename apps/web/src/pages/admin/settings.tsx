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
      <p className="text-sm text-muted-foreground">Slack messages always wait for David’s approval.</p>
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

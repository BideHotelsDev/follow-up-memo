import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X } from "lucide-react"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api, HttpError, type SkipRuleIn } from "@/lib/api"
import { cn } from "@/lib/utils"

const KINDS: [SkipRuleIn["type"], string, string][] = [
  ["title_keyword", "Title contains", "1:1, interview, investor"],
  ["attendee_email", "Attendee", "someone@example.com"],
]

function Editor({ initial }: { initial: SkipRuleIn[] }) {
  const queryClient = useQueryClient()
  const [rules, setRules] = useState(initial)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const save = useMutation({
    mutationFn: (next: SkipRuleIn[]) => api.putSkipRules(next),
    onSuccess: (saved) => {
      setRules(saved)
      queryClient.invalidateQueries({ queryKey: ["skip-rules"] })
      toast.success("Saved")
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {KINDS.map(([type, label, placeholder]) => (
        <div key={type} className={cn(surface, "grid content-start gap-3 p-5")}>
          <h3 className="font-sans text-base font-medium">{label}</h3>
          <div className="flex flex-wrap gap-2">
            {rules
              .filter((r) => r.type === type)
              .map((r) => (
                <span
                  key={r.value}
                  className="inline-flex items-center gap-1 rounded-full border bg-secondary py-1 pr-1 pl-3 text-sm"
                >
                  {r.value}
                  <button
                    aria-label={`Remove ${r.value}`}
                    className="rounded-full p-0.5 hover:bg-background"
                    onClick={() => save.mutate(rules.filter((x) => x !== r))}
                  >
                    <X className="size-3.5" />
                  </button>
                </span>
              ))}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              const value = (draft[type] ?? "").trim()
              if (!value) return
              save.mutate([...rules, { type, value }])
              setDraft((d) => ({ ...d, [type]: "" }))
            }}
          >
            <Input
              placeholder={placeholder}
              value={draft[type] ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, [type]: e.target.value }))}
              aria-label={label}
            />
            <Button type="submit" variant="outline">
              Add
            </Button>
          </form>
        </div>
      ))}
      <p className="text-sm text-muted-foreground md:col-span-2">
        Meetings matching any rule are never read. Matching ignores case.
      </p>
    </div>
  )
}

export default function SkipRulesPage() {
  const { data } = useQuery({ queryKey: ["skip-rules"], queryFn: api.skipRules })
  return data ? <Editor initial={data} /> : <Loading />
}

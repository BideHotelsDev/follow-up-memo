import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useApp } from "@/hooks/use-app"
import { api, HttpError, type ChannelMapIn } from "@/lib/api"
import { cn } from "@/lib/utils"

const CATEGORY = "category:"
const PROPERTY = "property:"

function Editor({ initial }: { initial: ChannelMapIn[] }) {
  const { properties, categories } = useApp()
  const queryClient = useQueryClient()
  const [rows, setRows] = useState<ChannelMapIn[]>(initial)
  const save = useMutation({
    mutationFn: () => api.putChannels(rows),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channels"] })
      toast.success("Saved")
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })
  const set = (i: number, patch: Partial<ChannelMapIn>) =>
    setRows((r) => r.map((row, j) => (j === i ? { ...row, ...patch } : row)))

  return (
    <div className="space-y-4">
      <div className={cn(surface, "divide-y")}>
        {rows.map((row, i) => (
          <div key={i} className="grid items-center gap-2 p-4 sm:grid-cols-[10rem_1fr_1fr_1fr_auto]">
            <Select
              value={row.category ? CATEGORY + row.category : row.property ? PROPERTY + row.property : undefined}
              onValueChange={(v) =>
                set(
                  i,
                  v.startsWith(CATEGORY)
                    ? { category: v.slice(CATEGORY.length), property: null }
                    : { property: v.slice(PROPERTY.length), category: null },
                )
              }
            >
              <SelectTrigger className="w-full" aria-label="Matches">
                <SelectValue placeholder="Choose…" />
              </SelectTrigger>
              <SelectContent>
                {categories
                  .filter((c) => c.is_active || c.name === row.category)
                  .map(({ name }) => (
                    <SelectItem key={CATEGORY + name} value={CATEGORY + name}>
                      {name}
                    </SelectItem>
                  ))}
                {properties.map(({ name: p }) => (
                  <SelectItem key={PROPERTY + p} value={PROPERTY + p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">
              {row.category
                ? `${row.category} meetings`
                : row.property
                  ? `Meetings about ${row.property}`
                  : "A category or a property"}
            </span>
            <Input
              placeholder="#channel name"
              value={row.slack_channel_name ?? ""}
              onChange={(e) => set(i, { slack_channel_name: e.target.value.replace(/^#/, "") })}
              aria-label="Channel name"
            />
            <Input
              className="mono"
              placeholder="Channel ID, C0123ABCD"
              value={row.slack_channel_id}
              onChange={(e) => set(i, { slack_channel_id: e.target.value.trim() })}
              aria-label="Channel ID"
            />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Remove"
              onClick={() => setRows((r) => r.filter((_, j) => j !== i))}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
        {!rows.length ? (
          <p className="p-4 text-muted-foreground">No channels yet: meetings get no channel digest.</p>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() =>
            setRows((r) => [...r, { category: null, property: null, slack_channel_id: "", slack_channel_name: "" }])
          }
        >
          <Plus className="size-4" /> Add channel
        </Button>
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending || rows.some((r) => !r.slack_channel_id || (!r.category && !r.property))}
        >
          Save
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        A meeting’s digest goes to its category’s channel, otherwise to its first property’s. Categories are set in
        Admin → Categories. The channel ID is in Slack under the channel’s name → About. For a private channel, invite
        the bot first.
      </p>
    </div>
  )
}

export default function ChannelsPage() {
  const { data } = useQuery({ queryKey: ["channels"], queryFn: api.channels })
  return data ? <Editor key={data.map((d) => d.id).join()} initial={data} /> : <Loading />
}

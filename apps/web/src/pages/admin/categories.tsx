import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { CategoryTag } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { api, HttpError, type Category, type CategoryIn } from "@/lib/api"
import { cn } from "@/lib/utils"

const fail = (err: unknown) => toast.error(err instanceof HttpError ? err.message : "Couldn't save")

const body = (c: Category, patch: Partial<CategoryIn> = {}): CategoryIn => ({
  name: c.name,
  description: c.description,
  is_sensitive: c.is_sensitive,
  is_active: c.is_active,
  ...patch,
})

function Row({
  category,
  first,
  last,
  save,
  move,
}: {
  category: Category
  first: boolean
  last: boolean
  save: (patch: Partial<CategoryIn>) => void
  move: (by: number) => void
}) {
  const [name, setName] = useState(category.name)
  const [about, setAbout] = useState(category.description ?? "")
  // Every save carries what's in the boxes, so a switch flipped straight after typing can't undo the typing.
  const send = (patch: Partial<CategoryIn>) =>
    save({ name: name.trim() || category.name, description: about.trim() || null, ...patch })
  return (
    <li className="grid gap-2 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <CategoryTag name={category.name} className={cn(!category.is_active && "border-dashed")} />
        {!category.is_active ? <span className="text-xs text-muted-foreground">Switched off</span> : null}
        <Input
          value={name}
          aria-label={`Name of ${category.name}`}
          className="h-9 min-w-40 flex-1"
          onChange={(e) => setName(e.target.value)}
          onBlur={() => name.trim() && name.trim() !== category.name && send({})}
        />
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Move ${category.name} up`}
          disabled={first}
          onClick={() => move(-1)}
        >
          <ArrowUp className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Move ${category.name} down`}
          disabled={last}
          onClick={() => move(1)}
        >
          <ArrowDown className="size-4" />
        </Button>
      </div>
      <Input
        value={about}
        placeholder="What belongs here, e.g. pricing, rates and OTAs"
        aria-label={`What ${category.name} covers`}
        className="h-9"
        onChange={(e) => setAbout(e.target.value)}
        onBlur={() => about.trim() !== (category.description ?? "") && send({})}
      />
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
        <label className="flex items-center gap-2">
          <Switch
            checked={category.is_sensitive}
            onCheckedChange={(on) => send({ is_sensitive: on })}
            aria-label={`${category.name} is sensitive`}
          />
          Sensitive: no team messages
        </label>
        <label className="flex items-center gap-2">
          <Switch
            checked={category.is_active}
            onCheckedChange={(on) => send({ is_active: on })}
            aria-label={`${category.name} in use`}
          />
          In use
        </label>
      </div>
    </li>
  )
}

export default function CategoriesPage() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ["admin-categories"], queryFn: api.adminCategories })
  const [name, setName] = useState("")
  const done = () => queryClient.invalidateQueries()
  const save = useMutation({
    mutationFn: ({ id, body }: { id: string; body: CategoryIn }) => api.updateCategory(id, body),
    onSuccess: done,
    onError: fail,
  })
  const create = useMutation({
    mutationFn: (body: CategoryIn) => api.addCategory(body),
    onSuccess: () => {
      setName("")
      done()
    },
    onError: fail,
  })
  if (!data) return <Loading />
  const move = (i: number, by: number) => {
    const a = data[i]
    const b = data[i + by]
    save.mutate({ id: a.id, body: body(a, { sort_order: b.sort_order }) })
    save.mutate({ id: b.id, body: body(b, { sort_order: a.sort_order }) })
  }

  return (
    <section className={cn(surface, "grid max-w-3xl content-start gap-4 p-5")}>
      <div>
        <h3 className="font-sans text-base font-medium">Meeting categories</h3>
        <p className="text-sm text-muted-foreground">
          Claude puts each meeting in the category that fits best, guided by what you write under its name. The category
          picks the meeting’s Slack channel (Admin → Channels) and drives the category filter on Meetings and Tasks. A
          sensitive category keeps its meetings out of team messages and the channel digest. A renamed category keeps
          its meetings; one switched off stays on past meetings but isn’t used for new ones.
        </p>
      </div>
      <ul className="divide-y">
        {data.map((c, i) => (
          <Row
            key={`${c.id}-${c.name}-${c.description}`}
            category={c}
            first={i === 0}
            last={i === data.length - 1}
            save={(patch) => save.mutate({ id: c.id, body: body(c, patch) })}
            move={(by) => move(i, by)}
          />
        ))}
        {!data.length ? <li className="py-3 text-muted-foreground">No categories yet.</li> : null}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (name.trim()) create.mutate({ name: name.trim(), is_active: true, is_sensitive: false })
        }}
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Add a category"
          aria-label="New category"
        />
        <Button type="submit" variant="outline" disabled={!name.trim() || create.isPending}>
          Add
        </Button>
      </form>
    </section>
  )
}

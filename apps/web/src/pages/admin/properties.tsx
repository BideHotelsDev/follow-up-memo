import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowDown, ArrowUp } from "lucide-react"
import { toast } from "sonner"

import { Loading, surface } from "@/components/page"
import { HotelTag } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { api, HttpError, type PropertyIn } from "@/lib/api"
import { cn } from "@/lib/utils"

type Row = { id: string; name: string; is_active: boolean; sort_order?: number }

const fail = (err: unknown) => toast.error(err instanceof HttpError ? err.message : "Couldn't save")

/** One editable list: rename in place, switch off, add; properties can also be put in order. */
function List({
  title,
  item,
  note,
  rows,
  add,
  update,
  ordered,
  tag,
}: {
  title: string
  item: string
  note: string
  rows: Row[]
  add: (body: PropertyIn) => Promise<unknown>
  update: (id: string, body: PropertyIn) => Promise<unknown>
  ordered?: boolean
  tag?: boolean
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState("")
  const [names, setNames] = useState<Record<string, string>>({})
  const done = () => queryClient.invalidateQueries()
  const save = useMutation({
    mutationFn: ({ id, body }: { id: string; body: PropertyIn }) => update(id, body),
    onSuccess: done,
    onError: fail,
  })
  const create = useMutation({
    mutationFn: (body: PropertyIn) => add(body),
    onSuccess: () => {
      setName("")
      done()
    },
    onError: fail,
  })
  const move = (i: number, by: number) => {
    const a = rows[i]
    const b = rows[i + by]
    save.mutate({ id: a.id, body: { name: a.name, is_active: a.is_active, sort_order: b.sort_order } })
    save.mutate({ id: b.id, body: { name: b.name, is_active: b.is_active, sort_order: a.sort_order } })
  }

  return (
    <section className={cn(surface, "grid content-start gap-4 p-5")}>
      <div>
        <h3 className="font-sans text-base font-medium">{title}</h3>
        <p className="text-sm text-muted-foreground">{note}</p>
      </div>
      <ul className="divide-y">
        {rows.map((row, i) => {
          const draft = names[row.id] ?? row.name
          return (
            <li key={row.id} className="flex flex-wrap items-center gap-2 py-2.5">
              {tag ? <HotelTag name={row.name} className={cn(!row.is_active && "opacity-50")} /> : null}
              <Input
                value={draft}
                aria-label={`Name of ${row.name}`}
                className="h-9 min-w-40 flex-1"
                onChange={(e) => setNames((n) => ({ ...n, [row.id]: e.target.value }))}
                onBlur={() =>
                  draft.trim() &&
                  draft.trim() !== row.name &&
                  save.mutate({ id: row.id, body: { name: draft.trim(), is_active: row.is_active } })
                }
              />
              {ordered ? (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Move ${row.name} up`}
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                  >
                    <ArrowUp className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Move ${row.name} down`}
                    disabled={i === rows.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    <ArrowDown className="size-4" />
                  </Button>
                </>
              ) : null}
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Switch
                  checked={row.is_active}
                  onCheckedChange={(on) => save.mutate({ id: row.id, body: { name: row.name, is_active: on } })}
                  aria-label={`${row.name} in use`}
                />
                In use
              </label>
            </li>
          )
        })}
      </ul>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (name.trim()) create.mutate({ name: name.trim(), is_active: true })
        }}
      >
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={`Add a ${item}`}
          aria-label={`New ${item}`}
        />
        <Button type="submit" variant="outline" disabled={!name.trim() || create.isPending}>
          Add
        </Button>
      </form>
    </section>
  )
}

export default function PropertiesPage() {
  const properties = useQuery({ queryKey: ["admin-properties"], queryFn: api.adminProperties })
  const systems = useQuery({ queryKey: ["admin-systems"], queryFn: api.adminSystems })
  if (!properties.data || !systems.data) return <Loading />
  return (
    <div className="grid items-start gap-4 lg:grid-cols-2">
      <List
        title="Properties"
        item="property"
        note="Claude tags each meeting with the properties it’s about; they drive the property filter and the channel map. A renamed property keeps its meetings and colour; one switched off stays on past meetings but isn’t used for new ones."
        rows={properties.data}
        add={api.addProperty}
        update={api.updateProperty}
        ordered
        tag
      />
      <List
        title="Systems"
        item="system"
        note="The tools Claude notes when a meeting mentions them, such as Mews or PriceLabs."
        rows={systems.data}
        add={api.addSystem}
        update={api.updateSystem}
      />
    </div>
  )
}

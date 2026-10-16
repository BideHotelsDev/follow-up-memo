import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, HttpError, type User, type UserIn } from "@/lib/api"

const ROLE_LABELS: Record<User["role"], string> = { owner: "Owner", admin: "Admin", member: "Member" }

const EMPTY: UserIn = { email: "", name: "", role: "member", slack_user_id: null, ownership_areas: [], is_active: true }

function PersonDialog({ person, onClose }: { person: User | "new"; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<UserIn>(person === "new" ? EMPTY : person)
  const [areas, setAreas] = useState((form.ownership_areas ?? []).join(", "))
  const save = useMutation({
    mutationFn: (body: UserIn) => (person === "new" ? api.addPerson(body) : api.updatePerson(person.id, body)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-people"] })
      toast.success("Saved")
      onClose()
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })
  const set = <K extends keyof UserIn>(key: K, value: UserIn[K]) => setForm((f) => ({ ...f, [key]: value }))

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{person === "new" ? "Add a person" : `Edit ${person.name}`}</DialogTitle>
        </DialogHeader>
        <form
          id="person"
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            const ownership_areas = areas
              .split(",")
              .map((a) => a.trim())
              .filter(Boolean)
            save.mutate({ ...form, slack_user_id: form.slack_user_id || null, ownership_areas })
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" value={form.name} onChange={(e) => set("name", e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role">Role</Label>
            <Select value={form.role} onValueChange={(v) => set("role", v as User["role"])}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="slack">Slack member ID</Label>
            <Input
              id="slack"
              className="mono"
              placeholder="U0123ABCD"
              value={form.slack_user_id ?? ""}
              onChange={(e) => set("slack_user_id", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="areas">Owns by default</Label>
            <Input
              id="areas"
              placeholder="housekeeping, Operto"
              value={areas}
              onChange={(e) => setAreas(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Comma-separated. Actions on these topics go to this person when the notes don't name an owner.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Switch id="active" checked={form.is_active} onCheckedChange={(v) => set("is_active", v)} />
            <Label htmlFor="active">Can sign in</Label>
          </div>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="person" disabled={save.isPending}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function PeoplePage() {
  const { data = [] } = useQuery({ queryKey: ["admin-people"], queryFn: api.adminPeople })
  const [editing, setEditing] = useState<User | "new" | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-2xl">People</h2>
          <p className="text-muted-foreground">Who can sign in, and who owns which kind of action.</p>
        </div>
        <Button onClick={() => setEditing("new")}>
          <Plus className="size-4" aria-hidden />
          Add person
        </Button>
      </div>
      <div className="overflow-x-auto rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Role</TableHead>
              <TableHead className="hidden sm:table-cell">Owns</TableHead>
              <TableHead className="hidden sm:table-cell">Slack</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((p) => (
              <TableRow key={p.id} className="cursor-pointer" onClick={() => setEditing(p)}>
                <TableCell>
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-muted-foreground">{p.email}</div>
                </TableCell>
                <TableCell>
                  {ROLE_LABELS[p.role]}
                  {!p.is_active ? (
                    <Badge variant="outline" className="ml-2">
                      Off
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell className="hidden text-sm sm:table-cell">{p.ownership_areas.join(", ") || "—"}</TableCell>
                <TableCell className="mono hidden text-sm sm:table-cell">{p.slack_user_id ?? "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {editing ? <PersonDialog person={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  )
}

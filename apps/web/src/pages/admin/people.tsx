import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { toast } from "sonner"

import { Empty, Loading } from "@/components/page"
import { Status } from "@/components/tags"
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

/** Phones get 44px controls; from md up they keep their usual size. */
const TOUCH = "max-md:h-11"

/**
 * While Bide Hub manages accounts, email, name, role and on/off come from the Hub; Slack ID and areas stay here.
 * `unsure` means we couldn't check who manages accounts, so the Hub's fields stay read-only to be safe.
 */
function PersonDialog({
  person,
  managed,
  hub,
  unsure,
  onClose,
}: {
  person: User | "new"
  managed: boolean
  hub?: string | null
  unsure: boolean
  onClose: () => void
}) {
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
          {managed ? (
            <>
              <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
                {unsure ? (
                  "Couldn't check whether Bide Hub manages accounts, so name, email, role and sign-in can't be changed right now. You can still change the Slack ID and areas."
                ) : (
                  <>
                    <span className="font-medium text-foreground">Managed in Bide Hub.</span> Change name, email, role
                    and sign-in{" "}
                    {hub ? (
                      <a className="underline underline-offset-4" href={`${hub}/admin/people`}>
                        in Bide Hub
                      </a>
                    ) : (
                      "in Bide Hub"
                    )}
                    . You can change the Slack ID and areas here.
                  </>
                )}
              </p>
              {person === "new" ? null : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  <dt className="text-muted-foreground">Name</dt>
                  <dd className="min-w-0 font-medium break-words">{person.name}</dd>
                  <dt className="text-muted-foreground">Email</dt>
                  <dd className="min-w-0 break-all">{person.email}</dd>
                  <dt className="text-muted-foreground">Role</dt>
                  <dd>{ROLE_LABELS[person.role]}</dd>
                  <dt className="text-muted-foreground">Can sign in</dt>
                  <dd>{person.is_active ? "Yes" : "No"}</dd>
                </dl>
              )}
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  className={TOUCH}
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  className={TOUCH}
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="role">Role</Label>
                <Select value={form.role} onValueChange={(v) => set("role", v as User["role"])}>
                  <SelectTrigger id="role" className={TOUCH}>
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
            </>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="slack">Slack member ID</Label>
            <Input
              id="slack"
              className={`mono ${TOUCH}`}
              placeholder="U0123ABCD"
              value={form.slack_user_id ?? ""}
              onChange={(e) => set("slack_user_id", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="areas">Owns by default</Label>
            <Input
              id="areas"
              className={TOUCH}
              placeholder="housekeeping, Operto"
              value={areas}
              onChange={(e) => setAreas(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Comma-separated. Actions on these topics go to this person when the notes don't name an owner.
            </p>
          </div>
          {managed ? null : (
            <div className="flex items-center gap-3 max-md:min-h-11">
              <Switch id="active" checked={form.is_active} onCheckedChange={(v) => set("is_active", v)} />
              <Label htmlFor="active">Can sign in</Label>
            </div>
          )}
        </form>
        <DialogFooter>
          <Button variant="outline" className={TOUCH} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="person" className={TOUCH} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function PeoplePage() {
  const people = useQuery({ queryKey: ["admin-people"], queryFn: api.adminPeople })
  const providers = useQuery({ queryKey: ["providers"], queryFn: api.providers, staleTime: Infinity })
  // Until we know who manages accounts, nothing opens. If we can't tell, the Hub's fields stay read-only.
  const ready = !providers.isPending
  const unsure = providers.isError
  const managed = unsure || (providers.data?.accounts_managed_by_hub ?? false)
  const hub = providers.data?.bide_hub_issuer
  const [editing, setEditing] = useState<User | "new" | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h2 className="text-2xl">People</h2>
            {managed && !unsure ? <Badge variant="outline">Managed in Bide Hub</Badge> : null}
          </div>
          <p className="text-muted-foreground">
            {unsure ? (
              <>
                Couldn't check whether Bide Hub manages accounts, so names, emails, roles and sign-in are read-only for
                now.{" "}
                <button type="button" className="underline underline-offset-4" onClick={() => providers.refetch()}>
                  Try again
                </button>
              </>
            ) : managed ? (
              <>
                Who can sign in, and with which role, is managed in{" "}
                {hub ? (
                  <a className="underline underline-offset-4" href={`${hub}/admin/people`}>
                    Bide Hub
                  </a>
                ) : (
                  "Bide Hub"
                )}
                . Here you set who owns which kind of action.
              </>
            ) : (
              "Who can sign in, and who owns which kind of action."
            )}
          </p>
        </div>
        {ready && !managed ? (
          <Button className={TOUCH} onClick={() => setEditing("new")}>
            <Plus className="size-4" aria-hidden />
            Add person
          </Button>
        ) : null}
      </div>
      {people.isPending ? (
        <Loading />
      ) : people.isError ? (
        <Empty>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              Couldn't load people.{" "}
              {people.error instanceof HttpError ? people.error.message : "Check your connection and try again."}
            </span>
            <Button variant="outline" className={TOUCH} onClick={() => people.refetch()} disabled={people.isFetching}>
              {people.isFetching ? "Trying…" : "Try again"}
            </Button>
          </div>
        </Empty>
      ) : people.data.length === 0 ? (
        <Empty>
          {managed
            ? "Nobody here yet. People added in Bide Hub show up here."
            : "Nobody here yet. Add the people who run meetings and own actions."}
        </Empty>
      ) : (
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
              {people.data.map((p) => (
                <TableRow key={p.id} className="relative">
                  <TableCell>
                    {/* Stretched over the whole row, so the row opens by click, tap or keyboard. */}
                    <button
                      type="button"
                      className="text-left font-medium outline-none after:absolute after:inset-0 after:content-[''] focus-visible:after:ring-2 focus-visible:after:ring-ring focus-visible:after:ring-inset enabled:cursor-pointer disabled:cursor-wait"
                      disabled={!ready}
                      onClick={() => setEditing(p)}
                    >
                      <span className="sr-only">Edit </span>
                      {p.name}
                    </button>
                    <div className="text-xs text-muted-foreground">{p.email}</div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      {ROLE_LABELS[p.role]}
                      {!p.is_active ? <Status tone="skip">Can't sign in</Status> : null}
                    </div>
                  </TableCell>
                  <TableCell className="hidden text-sm sm:table-cell">{p.ownership_areas.join(", ") || "—"}</TableCell>
                  <TableCell className="mono hidden text-sm sm:table-cell">{p.slack_user_id ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {editing ? (
        <PersonDialog person={editing} managed={managed} hub={hub} unsure={unsure} onClose={() => setEditing(null)} />
      ) : null}
    </div>
  )
}

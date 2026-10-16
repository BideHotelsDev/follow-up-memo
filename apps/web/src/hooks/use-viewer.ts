import { useQuery } from "@tanstack/react-query"

import { useMe } from "@/hooks/use-me"
import { useScope } from "@/hooks/use-scope"
import { api } from "@/lib/api"

/** Whether the page is for a reviewer (David or Admin) or a member: a member signed in, or David viewing as one. */
export function useViewer() {
  const me = useMe().data
  const { viewingAs } = useScope()
  const reviewer = me?.role === "owner" || me?.role === "admin"
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled: reviewer })
  const viewingMember =
    reviewer && Boolean(viewingAs) && people.data?.find((p) => p.id === viewingAs)?.role === "member"
  return { me, reviewer, people: people.data ?? [], asMember: !reviewer || viewingMember }
}

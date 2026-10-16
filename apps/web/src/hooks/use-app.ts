import { useQuery } from "@tanstack/react-query"

import { api, type AppSettings } from "@/lib/api"

const FALLBACK: AppSettings = { owner_name: "the owner", owner_email: null, properties: [], systems: [] }

/** The owner's name, the properties and the systems, as Bide set them in Admin. */
export function useApp(): AppSettings {
  const { data } = useQuery({ queryKey: ["app"], queryFn: api.app, staleTime: 5 * 60_000 })
  return data ?? FALLBACK
}

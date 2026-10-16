import { useQuery } from "@tanstack/react-query"

import { api, HttpError } from "@/lib/api"

/** The signed-in person; `null` when signed out (a 401), so callers can tell "signed out" from "loading". */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.me()
      } catch (err) {
        if (err instanceof HttpError && err.status === 401) return null
        throw err
      }
    },
    staleTime: 5 * 60_000,
  })
}

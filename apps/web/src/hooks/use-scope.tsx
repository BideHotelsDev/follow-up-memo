import { createContext, useContext, useMemo, useState } from "react"

import type { Scope } from "@/lib/api"

/** The hotel filter and the Viewing as switch, shared by every page and remembered in this browser for each person
who signs in (so one person's choice never carries over to the next). */
type ScopeState = {
  property: string | null
  setProperty: (p: string | null) => void
  viewingAs: string | null
  setViewingAs: (id: string | null) => void
  scope: Scope
}

const ScopeContext = createContext<ScopeState | null>(null)
function load(key: string): { property: string | null; viewingAs: string | null } {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "{}")
    return { property: saved.property ?? null, viewingAs: saved.viewingAs ?? null }
  } catch {
    return { property: null, viewingAs: null }
  }
}

function save(key: string, value: { property: string | null; viewingAs: string | null }) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // private windows and blocked storage: the choice just isn't remembered
  }
}

export function ScopeProvider({ userId, children }: { userId: string; children: React.ReactNode }) {
  const key = `bide.followup.scope.${userId}`
  const [state, setState] = useState(() => load(key))
  const value = useMemo<ScopeState>(() => {
    const update = (next: Partial<typeof state>) =>
      setState((current) => {
        const merged = { ...current, ...next }
        save(key, merged)
        return merged
      })
    return {
      ...state,
      setProperty: (property) => update({ property }),
      setViewingAs: (viewingAs) => update({ viewingAs }),
      scope: { property: state.property, as: state.viewingAs },
    }
  }, [state, key])
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>
}

export function useScope(): ScopeState {
  const value = useContext(ScopeContext)
  if (!value) throw new Error("useScope outside ScopeProvider")
  return value
}

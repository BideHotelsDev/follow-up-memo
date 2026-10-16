import { createContext, useContext, useMemo, useState } from "react"

import type { Scope } from "@/lib/api"

/** The hotel filter and the Viewing as switch, shared by every page and remembered in this browser. */
type ScopeState = {
  property: string | null
  setProperty: (p: string | null) => void
  viewingAs: string | null
  setViewingAs: (id: string | null) => void
  scope: Scope
}

const ScopeContext = createContext<ScopeState | null>(null)
const KEY = "bide.followup.scope"

function load(): { property: string | null; viewingAs: string | null } {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}")
    return { property: saved.property ?? null, viewingAs: saved.viewingAs ?? null }
  } catch {
    return { property: null, viewingAs: null }
  }
}

function save(value: { property: string | null; viewingAs: string | null }) {
  try {
    localStorage.setItem(KEY, JSON.stringify(value))
  } catch {
    // private windows and blocked storage: the choice just isn't remembered
  }
}

export function ScopeProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState(load)
  const value = useMemo<ScopeState>(() => {
    const update = (next: Partial<typeof state>) =>
      setState((current) => {
        const merged = { ...current, ...next }
        save(merged)
        return merged
      })
    return {
      ...state,
      setProperty: (property) => update({ property }),
      setViewingAs: (viewingAs) => update({ viewingAs }),
      scope: { property: state.property, as: state.viewingAs },
    }
  }, [state])
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>
}

export function useScope(): ScopeState {
  const value = useContext(ScopeContext)
  if (!value) throw new Error("useScope outside ScopeProvider")
  return value
}

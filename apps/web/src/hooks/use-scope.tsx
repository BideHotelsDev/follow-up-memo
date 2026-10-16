import { createContext, useContext, useMemo, useState } from "react"

import type { Scope } from "@/lib/api"

/** The property filter, shared by every page and remembered in this browser for each person who signs in. */
type ScopeState = {
  property: string | null
  setProperty: (p: string | null) => void
  scope: Scope
}

const ScopeContext = createContext<ScopeState | null>(null)

function load(key: string): string | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "{}").property ?? null
  } catch {
    return null
  }
}

function save(key: string, property: string | null) {
  try {
    localStorage.setItem(key, JSON.stringify({ property }))
  } catch {
    // private windows and blocked storage: the choice just isn't remembered
  }
}

export function ScopeProvider({ userId, children }: { userId: string; children: React.ReactNode }) {
  const key = `bide.followup.scope.${userId}`
  const [property, setState] = useState(() => load(key))
  const value = useMemo<ScopeState>(
    () => ({
      property,
      setProperty: (next) => {
        save(key, next)
        setState(next)
      },
      scope: { property },
    }),
    [property, key],
  )
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>
}

export function useScope(): ScopeState {
  const value = useContext(ScopeContext)
  if (!value) throw new Error("useScope outside ScopeProvider")
  return value
}

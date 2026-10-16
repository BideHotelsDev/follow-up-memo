import { LogOut, Menu, PlugZap, Users } from "lucide-react"
import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { useQueryClient } from "@tanstack/react-query"

import { BrandLockup } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { api, type User } from "@/lib/api"
import { cn } from "@/lib/utils"

type Item = { to: string; label: string; icon: typeof Users; roles: User["role"][] }

// Pages arrive with their phases (PRD §3): Today, Meetings, drafts and Tasks join this list in Phase 4.
const NAV: Item[] = [
  { to: "/admin/connections", label: "Connections", icon: PlugZap, roles: ["admin"] },
  { to: "/admin/people", label: "People", icon: Users, roles: ["admin"] },
]

function Nav({ me, onNavigate }: { me: User; onNavigate?: () => void }) {
  const queryClient = useQueryClient()
  const items = NAV.filter((item) => item.roles.includes(me.role))
  return (
    <div className="flex h-full flex-col gap-6 bg-sidebar p-4 text-sidebar-foreground">
      <BrandLockup />
      <nav className="flex flex-col gap-1" aria-label="Main">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm",
                isActive ? "bg-sidebar-accent text-sidebar-accent-foreground" : "hover:bg-sidebar-accent/60",
              )
            }
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto space-y-2 text-sm">
        <p className="truncate opacity-80">{me.name}</p>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-sidebar-foreground hover:bg-sidebar-accent"
          onClick={async () => {
            await api.logout()
            queryClient.setQueryData(["me"], null)
          }}
        >
          <LogOut className="size-4" aria-hidden />
          Sign out
        </Button>
      </div>
    </div>
  )
}

export function AppShell({ me }: { me: User }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[15rem_1fr]">
      <aside className="hidden md:block">
        <div className="sticky top-0 h-dvh">
          <Nav me={me} />
        </div>
      </aside>
      <header className="flex items-center justify-between bg-sidebar px-4 py-2 md:hidden">
        <BrandLockup compact />
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="text-sidebar-foreground" aria-label="Open menu">
              <Menu className="size-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 border-0 p-0">
            <SheetTitle className="sr-only">Menu</SheetTitle>
            <Nav me={me} onNavigate={() => setOpen(false)} />
          </SheetContent>
        </Sheet>
      </header>
      <main className="mx-auto w-full max-w-5xl px-4 py-6 md:px-8 md:py-10">
        <Outlet />
      </main>
    </div>
  )
}

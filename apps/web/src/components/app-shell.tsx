import { useQuery, useQueryClient } from "@tanstack/react-query"
import { LogOut, Settings2 } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"

import { SpiralPin, Wordmark } from "@/components/brand"
import { BIDE_WIDE, PROPERTIES } from "@/components/tags"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useScope } from "@/hooks/use-scope"
import { api, type User } from "@/lib/api"
import { time } from "@/lib/format"
import { cn } from "@/lib/utils"

const ALL = "all"

type Tab = { to: string; label: string; count?: number; hot?: boolean }

function Tabs({ tabs }: { tabs: Tab[] }) {
  return (
    <nav aria-label="Pages" className="-mx-3 flex gap-1 overflow-x-auto [scrollbar-width:none]">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.to === "/"}
          className={({ isActive }) =>
            cn(
              "inline-flex shrink-0 items-center gap-1.5 border-b-[3px] px-3 pt-2 pb-2.5 text-[15px]",
              isActive
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )
          }
        >
          {tab.label}
          {tab.count ? (
            <span
              className={cn(
                "tnum rounded-full px-1.5 text-xs font-medium",
                tab.hot ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
              )}
            >
              {tab.count}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell({ me }: { me: User }) {
  const queryClient = useQueryClient()
  const { property, setProperty, scope } = useScope()
  const reviewer = me.role !== "member"
  const today = useQuery({ queryKey: ["today", scope], queryFn: () => api.today(scope), refetchInterval: 60_000 })
  const counts = today.data?.counts
  const tabs: Tab[] = reviewer
    ? [
        { to: "/", label: "Today", count: counts?.questions, hot: true },
        { to: "/impact", label: "Impact" },
        { to: "/meetings", label: "Meetings" },
        { to: "/emails", label: "Email drafts", count: counts?.emails },
        { to: "/slack", label: "Slack drafts", count: counts?.slack },
        { to: "/tasks", label: "Tasks", count: counts?.tasks_open },
        { to: "/how", label: "How it works" },
      ]
    : [
        { to: "/", label: "Today" },
        { to: "/tasks", label: "Tasks", count: counts?.tasks_open },
        { to: "/how", label: "How it works" },
      ]
  if (me.role === "admin") tabs.push({ to: "/admin", label: "Admin" })

  const run = today.data?.last_run
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b bg-background/95 px-4 backdrop-blur">
        <div className="mx-auto max-w-6xl space-y-1 pt-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <SpiralPin className="size-7 shrink-0 text-primary" />
              <Wordmark className="text-2xl" showTrademark={false} />
              <span className="hidden truncate text-sm text-muted-foreground sm:inline">Meeting follow-up</span>
            </div>
            <div className="flex min-w-0 items-center gap-2">
              {run ? (
                <span className="hidden items-center gap-1.5 text-sm text-muted-foreground lg:inline-flex">
                  <span aria-hidden className={cn("size-2 rounded-full", run.error ? "bg-destructive" : "bg-ok")} />
                  Last run {time(run.started_at)}
                  {today.data?.next_run_at ? ` · next ${time(today.data.next_run_at)}` : ""}
                </span>
              ) : null}
              <Select value={property ?? ALL} onValueChange={(v) => setProperty(v === ALL ? null : v)}>
                <SelectTrigger aria-label="Property" className="h-9 w-auto rounded-full bg-card">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="end">
                  <SelectItem value={ALL}>All properties</SelectItem>
                  {[...PROPERTIES, BIDE_WIDE].map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="Account">
                    <Settings2 className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>{me.name}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={async () => {
                      await api.logout()
                      queryClient.setQueryData(["me"], null)
                    }}
                  >
                    <LogOut className="size-4" /> Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
          <Tabs tabs={tabs} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-8 md:py-10">
        <Outlet />
      </main>
    </div>
  )
}

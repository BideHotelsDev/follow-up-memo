import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BarChart3,
  CalendarDays,
  CircleHelp,
  Ellipsis,
  House,
  ListChecks,
  LogOut,
  Mail,
  MessageSquare,
  Settings2,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

import { SpiralPin, Wordmark } from "@/components/brand"
import { BIDE_WIDE, CategoryDot } from "@/components/tags"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useApp } from "@/hooks/use-app"
import { useScope } from "@/hooks/use-scope"
import { api, type User } from "@/lib/api"
import { time } from "@/lib/format"
import { cn } from "@/lib/utils"

const ALL = "all"

type Tab = {
  to: string
  label: string
  short?: string
  icon: LucideIcon
  count?: number
  hot?: boolean
  phone?: boolean
}

function Count({ tab, className }: { tab: Tab; className?: string }) {
  return tab.count ? (
    <span
      className={cn(
        "tnum rounded-full px-1.5 text-xs font-medium",
        tab.hot ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
        className,
      )}
    >
      {tab.count}
    </span>
  ) : null
}

/** Desktop and tablet: tabs under the wordmark. */
function Tabs({ tabs }: { tabs: Tab[] }) {
  return (
    <nav aria-label="Pages" className="-mx-3 hidden gap-1 md:flex">
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
          <Count tab={tab} />
        </NavLink>
      ))}
    </nav>
  )
}

const isActive = (pathname: string, to: string) => (to === "/" ? pathname === "/" : pathname.startsWith(to))

/** Phone: a tab bar under the thumb, the four pages David uses between calls, and the rest under More. */
function BottomBar({ tabs }: { tabs: Tab[] }) {
  const { pathname } = useLocation()
  const [more, setMore] = useState(false)
  const main = tabs.filter((t) => t.phone)
  const rest = tabs.filter((t) => !t.phone)
  const restActive = rest.some((t) => isActive(pathname, t.to))
  const item = "relative flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium"
  return (
    <nav
      aria-label="Pages"
      className="fixed inset-x-0 bottom-0 z-30 border-t bg-card/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      <div className="mx-auto flex max-w-md">
        {main.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === "/"}
            className={({ isActive }) => cn(item, isActive ? "text-foreground" : "text-muted-foreground")}
          >
            {({ isActive }) => (
              <>
                <span
                  aria-hidden
                  className={cn("absolute inset-x-5 top-0 h-[3px] rounded-b-full", isActive && "bg-primary")}
                />
                <span className="relative">
                  <tab.icon className="size-5" aria-hidden strokeWidth={isActive ? 2.25 : 1.75} />
                  <Count
                    tab={tab}
                    className="absolute -top-1.5 left-3.5 min-w-5 text-center leading-5 ring-2 ring-card"
                  />
                </span>
                {tab.short ?? tab.label}
              </>
            )}
          </NavLink>
        ))}
        {rest.length ? (
          <button
            type="button"
            onClick={() => setMore(true)}
            className={cn(item, restActive ? "text-foreground" : "text-muted-foreground")}
          >
            <span
              aria-hidden
              className={cn("absolute inset-x-5 top-0 h-[3px] rounded-b-full", restActive && "bg-primary")}
            />
            <Ellipsis className="size-5" aria-hidden />
            More
          </button>
        ) : null}
      </div>
      <Sheet open={more} onOpenChange={setMore}>
        <SheetContent side="bottom" className="rounded-t-2xl pb-[calc(env(safe-area-inset-bottom)+1rem)]">
          <SheetHeader className="pb-0">
            <SheetTitle className="font-display text-xl font-normal">More</SheetTitle>
            <SheetDescription className="sr-only">The other pages</SheetDescription>
          </SheetHeader>
          <ul className="grid gap-1 px-2">
            {rest.map((tab) => (
              <li key={tab.to}>
                <NavLink
                  to={tab.to}
                  onClick={() => setMore(false)}
                  className={({ isActive }) =>
                    cn(
                      "flex min-h-12 items-center gap-3 rounded-lg px-3 text-base",
                      isActive ? "bg-secondary font-medium text-foreground" : "text-foreground hover:bg-muted",
                    )
                  }
                >
                  <tab.icon className="size-5 text-muted-foreground" aria-hidden />
                  {tab.label}
                  <Count tab={tab} className="ml-auto" />
                </NavLink>
              </li>
            ))}
          </ul>
        </SheetContent>
      </Sheet>
    </nav>
  )
}

/** The router changes the URL but doesn't scroll: go to the #section a link names, once the page has drawn it. */
function useScrollToHash() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (!hash) return
    let tries = 0
    const timer = setInterval(() => {
      const el = document.getElementById(decodeURIComponent(hash.slice(1)))
      if (el || ++tries > 20) clearInterval(timer)
      el?.scrollIntoView({ block: "start" })
    }, 100)
    return () => clearInterval(timer)
  }, [pathname, hash])
}

export function AppShell({ me }: { me: User }) {
  useScrollToHash()
  const queryClient = useQueryClient()
  const { property, setProperty, scope } = useScope()
  const reviewer = me.role !== "member"
  const { properties } = useApp()
  const today = useQuery({ queryKey: ["today", scope], queryFn: () => api.today(scope), refetchInterval: 60_000 })
  const counts = today.data?.counts
  const tabs: Tab[] = reviewer
    ? [
        { to: "/", label: "Today", icon: House, count: counts?.questions, hot: true, phone: true },
        { to: "/impact", label: "Impact", icon: BarChart3 },
        { to: "/meetings", label: "Meetings", icon: CalendarDays },
        { to: "/emails", label: "Email drafts", short: "Emails", icon: Mail, count: counts?.emails, phone: true },
        { to: "/slack", label: "Slack drafts", short: "Slack", icon: MessageSquare, count: counts?.slack, phone: true },
        { to: "/tasks", label: "Tasks", icon: ListChecks, count: counts?.tasks_open, phone: true },
        { to: "/how", label: "How it works", icon: CircleHelp },
      ]
    : [
        { to: "/", label: "Today", icon: House, phone: true },
        { to: "/tasks", label: "Tasks", icon: ListChecks, count: counts?.tasks_open, phone: true },
        { to: "/how", label: "How it works", icon: CircleHelp, phone: true },
      ]
  if (me.role !== "member") tabs.push({ to: "/admin", label: "Admin", icon: SlidersHorizontal })

  const run = today.data?.last_run
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b bg-background/95 px-4 backdrop-blur">
        <div className="mx-auto max-w-6xl space-y-1 py-2.5 md:pb-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <SpiralPin className="size-6 shrink-0 text-primary md:size-7" />
              <Wordmark className="text-xl md:text-2xl" showTrademark={false} />
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
                  {[...properties, { name: BIDE_WIDE, color: null }].map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      <CategoryDot slot={p.color} className="rounded-[3px]" />
                      {p.name}
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
      <main className="mx-auto w-full max-w-6xl px-4 pt-6 pb-28 md:py-10">
        <Outlet />
      </main>
      <BottomBar tabs={tabs} />
    </div>
  )
}

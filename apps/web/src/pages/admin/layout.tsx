import { NavLink, Outlet } from "react-router-dom"

import { PageHead } from "@/components/page"
import { cn } from "@/lib/utils"

const TABS: [string, string][] = [
  ["connections", "Connections"],
  ["people", "People"],
  ["properties", "Properties"],
  ["categories", "Categories"],
  ["channels", "Channels"],
  ["skip-rules", "Skip rules"],
  ["settings", "Claude, email and schedule"],
  ["runs", "Run log"],
]

export default function AdminLayout() {
  return (
    <>
      <PageHead title="Admin" lede="Who the app knows, where messages go, and how runs are going." />
      <nav
        aria-label="Admin"
        className="-mx-1 mb-8 flex flex-nowrap gap-2 overflow-x-auto px-1 pb-1 md:flex-wrap md:overflow-visible"
      >
        {TABS.map(([to, label]) => (
          <NavLink
            key={to}
            to={`/admin/${to}`}
            className={({ isActive }) =>
              cn(
                "shrink-0 rounded-full border px-3.5 py-1.5 text-sm whitespace-nowrap max-md:py-3",
                isActive ? "border-foreground bg-foreground text-background" : "bg-card hover:border-foreground/40",
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  )
}

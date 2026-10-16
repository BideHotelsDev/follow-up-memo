import { NavLink, Outlet } from "react-router-dom"

import { PageHead } from "@/components/page"
import { cn } from "@/lib/utils"

const TABS: [string, string][] = [
  ["connections", "Connections"],
  ["people", "People"],
  ["properties", "Properties"],
  ["channels", "Channels"],
  ["skip-rules", "Skip rules"],
  ["settings", "Email and schedule"],
  ["runs", "Run log"],
]

export default function AdminLayout() {
  return (
    <>
      <PageHead title="Admin" lede="Who the app knows, where messages go, and how runs are going." />
      <nav aria-label="Admin" className="mb-8 flex flex-wrap gap-2">
        {TABS.map(([to, label]) => (
          <NavLink
            key={to}
            to={`/admin/${to}`}
            className={({ isActive }) =>
              cn(
                "rounded-full border px-3.5 py-1.5 text-sm",
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

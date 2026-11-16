import { Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"

/** The app's name as it appears in index.html, after the page in every tab title. */
export const APP_NAME = "bide Follow-up"

export function PageHead({
  eyebrow,
  title,
  documentTitle,
  lede,
  children,
}: {
  eyebrow?: string
  title: string
  /** The tab title, when the H1 is not a good one (the greeting on Today, say). Defaults to `title`. */
  documentTitle?: string
  lede?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      {/* React 19 hoists this into <head>, so each page names its own tab and history entry. */}
      <title>{`${documentTitle ?? title} · ${APP_NAME}`}</title>
      <div className="space-y-2">
        {eyebrow ? <p className="eyebrow text-muted-foreground">{eyebrow}</p> : null}
        <h1 className="text-3xl md:text-4xl">{title}</h1>
        {lede ? <p className="max-w-2xl text-lg text-muted-foreground">{lede}</p> : null}
      </div>
      {children}
    </div>
  )
}

export function SectionTitle({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3">
      <h2 className="text-2xl">{title}</h2>
      {children}
    </div>
  )
}

export function Loading({ className }: { className?: string }) {
  return (
    <div className={cn("flex justify-center py-16", className)} aria-busy>
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
    </div>
  )
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border bg-card p-6 text-muted-foreground">{children}</div>
}

/** A card's surface, as the demo draws it: white, hairline border, a soft shadow. */
export const surface = "rounded-xl border bg-card shadow-[0_8px_30px_rgba(23,45,35,0.06)]"

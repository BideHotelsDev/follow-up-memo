import { Loader2 } from "lucide-react"

import { cn } from "@/lib/utils"

export function PageHead({
  eyebrow,
  title,
  lede,
  children,
}: {
  eyebrow?: string
  title: string
  lede?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
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

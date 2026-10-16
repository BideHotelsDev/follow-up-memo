import { cn } from "@/lib/utils"

import { useApp } from "@/hooks/use-app"

/** The property filter's name for meetings tagged with no property. */
export const BIDE_WIDE = "Bide-wide"

// Written out in full so Tailwind sees every class.
const SLOTS = [
  "bg-tag-0-subtle text-tag-0",
  "bg-tag-1-subtle text-tag-1",
  "bg-tag-2-subtle text-tag-2",
  "bg-tag-3-subtle text-tag-3",
  "bg-tag-4-subtle text-tag-4",
  "bg-tag-5-subtle text-tag-5",
]
const NEUTRAL = "bg-bide-subtle text-bide"

/** A property's tag, in the colour slot it keeps for good (Admin → Properties). */
export function HotelTag({ name, className }: { name: string; className?: string }) {
  const { properties } = useApp()
  const slot = properties.find((p) => p.name === name)?.color
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        slot === undefined ? NEUTRAL : SLOTS[slot % SLOTS.length],
        className,
      )}
    >
      {name}
    </span>
  )
}

/** A meeting's property tags; a meeting with none is Bide-wide. */
export function HotelTags({ properties }: { properties: string[] }) {
  const names = properties.length ? properties : [BIDE_WIDE]
  return (
    <>
      {names.map((p) => (
        <HotelTag key={p} name={p} />
      ))}
    </>
  )
}

type Tone = "done" | "wait" | "late" | "quiet" | "skip"

const DOT: Record<Tone, string> = {
  done: "bg-ok",
  wait: "bg-primary",
  late: "bg-destructive",
  quiet: "bg-border",
  skip: "border border-muted-foreground bg-transparent",
}
const TEXT: Record<Tone, string> = {
  done: "text-muted-foreground",
  wait: "text-attention-foreground dark:text-attention",
  late: "font-medium text-destructive",
  quiet: "text-muted-foreground",
  skip: "text-muted-foreground",
}

/** Status as quiet text with a dot, so property tags stay the only pills (as in the demo). */
export function Status({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm whitespace-nowrap", TEXT[tone])}>
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full", DOT[tone])} />
      {children}
    </span>
  )
}

const MEETING: Record<string, [Tone, string]> = {
  done: ["done", "Followed up"],
  partial: ["wait", "Some drafts failed"],
  failed: ["late", "Couldn't process"],
  queued: ["wait", "In the next run"],
  processing: ["wait", "Processing"],
  waiting: ["wait", "Waiting for Claude"],
  skipped: ["skip", "Skipped"],
}

export function MeetingStatus({ status }: { status: string }) {
  const [tone, label] = MEETING[status] ?? ["quiet", status]
  return <Status tone={tone}>{label}</Status>
}

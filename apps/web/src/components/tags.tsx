import { cn } from "@/lib/utils"

/** The hotel filter's choices: the three properties, and meetings tagged with none. */
export const PROPERTIES = ["The View", "The Hearth", "The Villa"] as const
export const BIDE_WIDE = "Bide-wide"

const STYLE: Record<string, string> = {
  "The View": "bg-view-subtle text-view",
  "The Hearth": "bg-hearth-subtle text-hearth",
  "The Villa": "bg-villa-subtle text-villa",
  [BIDE_WIDE]: "bg-bide-subtle text-bide",
}

export function HotelTag({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        STYLE[name] ?? STYLE[BIDE_WIDE],
        className,
      )}
    >
      {name}
    </span>
  )
}

/** A meeting's hotel tags; a meeting with none is Bide-wide. */
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

/** Status as quiet text with a dot, so hotel tags stay the only pills (as in the demo). */
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

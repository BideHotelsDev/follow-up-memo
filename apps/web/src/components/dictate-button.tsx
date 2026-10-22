import { useEffect, useRef, useState, type RefObject } from "react"
import { Loader2, Mic, Square } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { useApp } from "@/hooks/use-app"
import { startDictation, type Dictation, type DictationContext } from "@/lib/dictation"
import { cn } from "@/lib/utils"

type State = "idle" | "starting" | "listening" | "writing"

/**
 * Dictate into a box with Wispr Flow's voice API: press to talk, press again and Wispr's text goes in at the cursor
 * (replacing any selection). Hidden unless Admin has set up the API (WISPR_API_KEY).
 */
export function DictateButton({
  target,
  value,
  onChange,
  kind = "other",
  compact = false,
  className,
}: {
  target: RefObject<HTMLTextAreaElement | null>
  value: string
  onChange: (value: string) => void
  kind?: DictationContext["kind"]
  /** Icon only below the sm breakpoint, for a box with a button beside it on a phone. */
  compact?: boolean
  className?: string
}) {
  const { dictation: enabled } = useApp()
  const [state, setState] = useState<State>("idle")
  const session = useRef<Dictation | null>(null)
  const range = useRef<[number, number]>([0, 0])
  const latest = useRef(value)
  latest.current = value

  useEffect(() => () => session.current?.cancel(), [])

  if (!enabled) return null

  async function start() {
    const box = target.current
    const at: [number, number] = box ? [box.selectionStart, box.selectionEnd] : [value.length, value.length]
    range.current = at
    setState("starting")
    try {
      session.current = await startDictation(
        { kind, before: value.slice(0, at[0]), selected: value.slice(at[0], at[1]), after: value.slice(at[1]) },
        () => void finish(),
      )
      setState("listening")
    } catch (e) {
      setState("idle")
      const denied = e instanceof DOMException && e.name === "NotAllowedError"
      toast.error(denied ? "Allow the microphone to dictate." : "Couldn't start dictation. Try again, or type.")
    }
  }

  async function finish() {
    const current = session.current
    if (!current) return
    session.current = null
    setState("writing")
    try {
      const text = await current.finish()
      if (text) {
        const [from, to] = range.current
        const now = latest.current
        onChange(now.slice(0, from) + text + now.slice(to))
        requestAnimationFrame(() => {
          target.current?.focus()
          target.current?.setSelectionRange(from + text.length, from + text.length)
        })
      } else {
        toast("Wispr Flow didn't hear anything.")
      }
    } catch {
      toast.error("Wispr Flow couldn't write that up. Try again, or type.")
    } finally {
      setState("idle")
    }
  }

  const listening = state === "listening"
  const busy = state === "starting" || state === "writing"
  return (
    <>
      <Button
        type="button"
        variant={listening ? "default" : "outline"}
        size="sm"
        onClick={() => (listening ? void finish() : void start())}
        disabled={busy}
        aria-pressed={listening}
        aria-label={listening ? "Stop and insert" : "Dictate with Wispr Flow"}
        title={listening ? "Stop and insert" : "Dictate with Wispr Flow"}
        className={cn("shrink-0 gap-1.5", className)}
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : listening ? (
          <Square className="size-3.5 fill-current" aria-hidden />
        ) : (
          <Mic className="size-4" aria-hidden />
        )}
        <span className={cn(compact && "hidden sm:inline")}>
          {listening ? "Stop" : state === "writing" ? "Writing" : "Dictate"}
        </span>
        {listening ? <span aria-hidden className="size-2 animate-pulse rounded-full bg-primary-foreground" /> : null}
      </Button>
      <span className="sr-only" role="status" aria-live="polite">
        {listening ? "Listening" : state === "writing" ? "Writing it up" : ""}
      </span>
    </>
  )
}

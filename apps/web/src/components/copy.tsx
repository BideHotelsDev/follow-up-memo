import { useState } from "react"
import { Check, Copy } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function CopyButton({
  text,
  label = "Copy",
  what,
  variant = "outline",
  className,
}: {
  text: string
  label?: string
  what: string
  variant?: "outline" | "default" | "ghost"
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      variant={variant}
      size="sm"
      className={className}
      aria-label={label === "Copy" ? `Copy ${what}` : undefined}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        } catch {
          toast.error(`Couldn't copy the ${what}. Select it and copy it instead.`)
        }
      }}
    >
      {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
      {copied ? "Copied" : label}
    </Button>
  )
}

/** A value to paste somewhere else: its name, the value in mono, and a copy button. */
export function CopyField({ name, value, secret }: { name: string; value: string; secret?: boolean }) {
  return (
    <div className="grid gap-1">
      <span className="eyebrow text-muted-foreground">{name}</span>
      <div className="flex min-w-0 items-center gap-2 rounded-lg border bg-background py-1 pr-1 pl-3">
        <code className={cn("mono min-w-0 flex-1 truncate text-sm", secret && "select-all")}>{value}</code>
        <CopyButton text={value} what={name} variant="ghost" />
      </div>
    </div>
  )
}

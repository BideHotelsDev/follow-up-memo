import { useState } from "react"
import { Check, ChevronsUpDown, X, type LucideIcon } from "lucide-react"

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export type PickerOption = {
  value: string
  label: string
  /** A second line: what the option covers. */
  hint?: string | null
  /** Drawn before the label: a colour dot, an avatar letter. */
  lead?: React.ReactNode
  /** Drawn after the label: a lock for a sensitive category. */
  trail?: React.ReactNode
  group?: string
}

/**
 * A filter that may hold many options: a searchable list (type to narrow, arrows and Enter to pick) with each
 * option's colour and description, grouped. An active filter shows on the trigger and clears in one tap.
 */
export function FilterPicker({
  label,
  icon: Icon,
  allLabel,
  value,
  onChange,
  options,
  search = "Search",
  className,
}: {
  label: string
  icon: LucideIcon
  allLabel: string
  value: string | null
  onChange: (value: string | null) => void
  options: PickerOption[]
  search?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const current = options.find((o) => o.value === value)
  const groups = [...new Set(options.map((o) => o.group ?? ""))]
  const pick = (v: string | null) => {
    onChange(v)
    setOpen(false)
  }
  return (
    <div className={cn("relative min-w-0", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            role="combobox"
            aria-expanded={open}
            aria-label={label}
            className={cn(
              "flex h-9 w-full min-w-0 items-center gap-2 rounded-md border border-input bg-card pr-9 pl-3 text-left text-sm shadow-xs transition-[border-color,box-shadow] outline-none hover:border-foreground/30 focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50",
              current && "border-foreground/40 bg-secondary",
              open && "border-foreground/40",
            )}
          >
            {current?.lead ?? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />}
            <span className={cn("truncate", current ? "font-medium text-foreground" : "text-foreground")}>
              {current?.label ?? allLabel}
            </span>
          </button>
        </PopoverTrigger>
        {current ? (
          <button
            type="button"
            onClick={() => onChange(null)}
            aria-label={`Clear ${label.toLowerCase()} filter`}
            className="absolute top-1/2 right-1 grid size-7 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:bg-background hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : (
          <ChevronsUpDown
            className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
        )}
        <PopoverContent
          align="start"
          className="w-[max(var(--radix-popover-trigger-width),18rem)] overflow-hidden rounded-lg p-0 shadow-lg"
        >
          <Command>
            {options.length > 6 ? <CommandInput placeholder={search} /> : null}
            <CommandList className="max-h-[min(22rem,60dvh)]">
              <CommandEmpty>Nothing matches.</CommandEmpty>
              <CommandGroup>
                <CommandItem value={`__all ${allLabel}`} onSelect={() => pick(null)} className="min-h-9">
                  <Icon className="size-4 text-muted-foreground" aria-hidden />
                  <span className="flex-1">{allLabel}</span>
                  {!current ? <Check className="size-4" aria-hidden /> : null}
                </CommandItem>
              </CommandGroup>
              {groups.map((group) => (
                <div key={group || "options"}>
                  <CommandSeparator />
                  <CommandGroup heading={group || undefined}>
                    {options
                      .filter((o) => (o.group ?? "") === group)
                      .map((o) => (
                        <CommandItem
                          key={o.value}
                          value={`${o.label} ${o.hint ?? ""}`}
                          onSelect={() => pick(o.value)}
                          className="min-h-9 items-start py-2"
                        >
                          <span className="mt-1 flex shrink-0">{o.lead}</span>
                          <span className="grid min-w-0 flex-1 gap-0.5">
                            <span className="flex items-center gap-1.5 text-foreground">
                              {o.label}
                              {o.trail}
                            </span>
                            {o.hint ? (
                              <span className="line-clamp-2 text-xs text-muted-foreground">{o.hint}</span>
                            ) : null}
                          </span>
                          {o.value === value ? <Check className="mt-0.5 size-4" aria-hidden /> : null}
                        </CommandItem>
                      ))}
                  </CommandGroup>
                </div>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}

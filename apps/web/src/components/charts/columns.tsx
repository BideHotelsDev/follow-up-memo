import { useState } from "react"

import { Tooltip, type Tip } from "@/components/charts/tooltip"
import type { Part } from "@/components/charts/bars"

export type Column = { label: string; parts: Part[]; note?: string }

/**
 * One stacked column per week (2px surface gaps, rounded top), on one axis from zero, with a legend carrying the
 * totals. Hover or focus a segment for its number; the weekly table sits under the chart for reading exactly.
 */
export function Columns({ columns, label }: { columns: Column[]; label: string }) {
  const [tip, setTip] = useState<Tip>(null)
  const max = Math.max(1, ...columns.map((c) => c.parts.reduce((s, p) => s + p.value, 0)))
  const keys = columns[0]?.parts ?? []
  const show = (e: { clientX: number; clientY: number }, c: Column, p: Part) =>
    setTip({
      x: e.clientX,
      y: e.clientY,
      value: String(p.value),
      label: `${p.label} · week of ${c.label}`,
      key: p.color,
    })
  return (
    <div className="grid gap-4">
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {keys.map((k) => (
          <li key={k.label} className="inline-flex items-center gap-2">
            <span aria-hidden className="size-3 rounded-[3px]" style={{ background: k.color }} />
            {k.label}
            <b className="tnum font-semibold text-foreground">
              {columns.reduce((s, c) => s + (c.parts.find((p) => p.label === k.label)?.value ?? 0), 0)}
            </b>
          </li>
        ))}
      </ul>
      <div role="img" aria-label={label} className="relative">
        <div aria-hidden className="absolute inset-x-0 top-0 border-t border-dashed" />
        <span aria-hidden className="tnum absolute -top-2.5 right-0 bg-card pl-1 text-xs text-muted-foreground">
          {max}
        </span>
        <div className="flex h-40 items-end gap-1.5 border-b pt-3 sm:gap-2">
          {columns.map((c) => (
            <div key={c.label} className="flex h-full min-w-0 flex-1 flex-col-reverse gap-0.5">
              {c.parts
                .filter((p) => p.value > 0)
                .map((p, i, shown) => (
                  <span
                    key={p.label}
                    role="img"
                    tabIndex={0}
                    aria-label={`Week of ${c.label}, ${p.label}: ${p.value}`}
                    className="block w-full outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-ring"
                    style={{
                      height: `${(100 * p.value) / max}%`,
                      minHeight: 3,
                      background: p.color,
                      borderRadius: i === shown.length - 1 ? "4px 4px 0 0" : 0,
                    }}
                    onPointerMove={(e) => show(e, c, p)}
                    onPointerLeave={() => setTip(null)}
                    onFocus={(e) => {
                      const box = e.currentTarget.getBoundingClientRect()
                      show({ clientX: box.left, clientY: box.top }, c, p)
                    }}
                    onBlur={() => setTip(null)}
                  />
                ))}
            </div>
          ))}
        </div>
        <div aria-hidden className="mt-1.5 flex gap-1.5 sm:gap-2">
          {columns.map((c, i) => (
            <span key={c.label} className="tnum min-w-0 flex-1 truncate text-center text-xs text-muted-foreground">
              {i % Math.ceil(columns.length / 6) === 0 || i === columns.length - 1 ? c.label : ""}
            </span>
          ))}
        </div>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}

import { useState } from "react"

import { Tooltip, type Tip } from "@/components/charts/tooltip"

export type Part = { label: string; value: number; color: string }

function pct(n: number, total: number) {
  return total ? Math.round((100 * n) / total) : 0
}

/** Parts of a whole as one stacked bar (2px surface gaps, rounded ends), with a legend carrying every count. */
export function StackedBar({ parts, label }: { parts: Part[]; label: string }) {
  const [tip, setTip] = useState<Tip>(null)
  const total = parts.reduce((sum, p) => sum + p.value, 0)
  const shown = parts.filter((p) => p.value > 0)
  return (
    <div className="space-y-4">
      <div
        className="flex h-6 gap-0.5"
        role="img"
        aria-label={`${label}: ${parts.map((p) => `${p.label} ${p.value}`).join(", ")}`}
      >
        {shown.length ? (
          shown.map((p, i) => (
            <span
              key={p.label}
              role="img"
              tabIndex={0}
              aria-label={`${p.label}: ${p.value}`}
              className="block h-full min-w-1 outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-ring"
              style={{
                flex: p.value,
                background: p.color,
                borderRadius: `${i === 0 ? 4 : 0}px ${i === shown.length - 1 ? 4 : 0}px ${i === shown.length - 1 ? 4 : 0}px ${i === 0 ? 4 : 0}px`,
              }}
              onPointerMove={(e) =>
                setTip({
                  x: e.clientX,
                  y: e.clientY,
                  value: String(p.value),
                  label: `${p.label} · ${pct(p.value, total)}%`,
                  key: p.color,
                })
              }
              onPointerLeave={() => setTip(null)}
              onFocus={(e) => {
                const box = e.currentTarget.getBoundingClientRect()
                setTip({
                  x: box.left,
                  y: box.bottom,
                  value: String(p.value),
                  label: `${p.label} · ${pct(p.value, total)}%`,
                  key: p.color,
                })
              }}
              onBlur={() => setTip(null)}
            />
          ))
        ) : (
          <span className="block h-full flex-1 rounded bg-secondary" />
        )}
      </div>
      <ul className="divide-y text-sm">
        {parts.map((p) => (
          <li key={p.label} className="grid grid-cols-[0.75rem_1fr_auto_2.75rem] items-center gap-3 py-2">
            <span aria-hidden className="size-3 rounded-[3px]" style={{ background: p.color }} />
            <span>{p.label}</span>
            <span className="tnum text-right font-semibold text-foreground">{p.value}</span>
            <span className="tnum text-right text-muted-foreground">{pct(p.value, total)}%</span>
          </li>
        ))}
      </ul>
      <Tooltip tip={tip} />
    </div>
  )
}

export type Row = { label: string; parts: Part[] }

/** One horizontal stacked bar per row, scaled to the largest row, the total at the bar's end. */
export function RowBars({ rows, keyParts }: { rows: Row[]; keyParts: Omit<Part, "value">[] }) {
  const [tip, setTip] = useState<Tip>(null)
  const max = Math.max(1, ...rows.map((r) => r.parts.reduce((s, p) => s + p.value, 0)))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {keyParts.map((k) => (
          <span key={k.label} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="size-3 rounded-[3px]" style={{ background: k.color }} />
            {k.label}
          </span>
        ))}
      </div>
      <div className="grid gap-3">
        {rows.map((r) => {
          const total = r.parts.reduce((s, p) => s + p.value, 0)
          const shown = r.parts.filter((p) => p.value > 0)
          return (
            <div key={r.label} className="grid grid-cols-[6.5rem_minmax(0,1fr)_2rem] items-center gap-3 text-sm">
              <span className="truncate">{r.label}</span>
              <div className="flex h-5 gap-0.5" style={{ width: `${(100 * total) / max}%` }}>
                {shown.map((p, i) => (
                  <span
                    key={p.label}
                    role="img"
                    tabIndex={0}
                    aria-label={`${r.label}, ${p.label}: ${p.value}`}
                    className="block h-full outline-none hover:brightness-110 focus-visible:ring-2 focus-visible:ring-ring"
                    style={{
                      flex: p.value,
                      background: p.color,
                      borderRadius: i === shown.length - 1 ? "0 4px 4px 0" : 0,
                    }}
                    onPointerMove={(e) =>
                      setTip({
                        x: e.clientX,
                        y: e.clientY,
                        value: String(p.value),
                        label: `${r.label} · ${p.label.toLowerCase()}`,
                        key: p.color,
                      })
                    }
                    onPointerLeave={() => setTip(null)}
                    onFocus={(e) => {
                      const box = e.currentTarget.getBoundingClientRect()
                      setTip({
                        x: box.left,
                        y: box.bottom,
                        value: String(p.value),
                        label: `${r.label} · ${p.label.toLowerCase()}`,
                        key: p.color,
                      })
                    }}
                    onBlur={() => setTip(null)}
                  />
                ))}
              </div>
              <span className="tnum text-right font-semibold text-foreground">{total}</span>
            </div>
          )
        })}
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}

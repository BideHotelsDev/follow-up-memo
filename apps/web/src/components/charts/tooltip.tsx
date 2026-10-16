/** One floating readout for every chart: the value leads, the label follows (text tokens, never series color). */
export type Tip = { x: number; y: number; value: string; label: string; key?: string } | null

export function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null
  return (
    <div
      role="tooltip"
      className="pointer-events-none fixed z-50 max-w-60 rounded-lg border bg-card px-3 py-2 text-sm text-muted-foreground shadow-lg"
      style={{ left: tip.x + 14, top: tip.y + 14 }}
    >
      <b className="block text-lg leading-tight font-semibold text-foreground">{tip.value}</b>
      <span className="inline-flex items-center gap-1.5">
        {tip.key ? (
          <span aria-hidden className="inline-block h-0.5 w-3 rounded" style={{ background: tip.key }} />
        ) : null}
        {tip.label}
      </span>
    </div>
  )
}

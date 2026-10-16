import { useState } from "react"

import { Tooltip, type Tip } from "@/components/charts/tooltip"
import { useWidth } from "@/components/charts/use-width"
import { day } from "@/lib/format"

export type RatePoint = { week: string; rate: number | null; detail: string; inProgress: boolean }

const LINE = "var(--chart-1)" // Fir Green: the one series
const GRID = "var(--border)"

/** Weekly percentage as a single 2px line on a fixed 0–100% axis. Weeks with no meetings leave a gap, not a zero. */
export function RateLine({ points, label }: { points: RatePoint[]; label: string }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const [tip, setTip] = useState<Tip>(null)
  const height = width < 480 ? 210 : 240
  const m = { top: 24, right: width < 480 ? 36 : 48, bottom: 30, left: 40 }
  const w = width - m.left - m.right
  const h = height - m.top - m.bottom
  const x = (i: number) => m.left + (points.length > 1 ? (i / (points.length - 1)) * w : w / 2)
  const y = (v: number) => m.top + h - (v / 100) * h

  // Break the line where a week had no meetings.
  const segments: number[][] = []
  points.forEach((p, i) => {
    if (p.rate === null) return
    const last = segments.at(-1)
    if (last && last.at(-1) === i - 1) last.push(i)
    else segments.push([i])
  })
  const lastIndex = [...points.keys()].reverse().find((i) => points[i].rate !== null)
  const tickEvery = width < 480 ? Math.ceil(points.length / 4) : Math.ceil(points.length / 8)

  function show(i: number, clientX: number, clientY: number) {
    setHover(i)
    const p = points[i]
    setTip({
      x: clientX,
      y: clientY,
      value: p.rate === null ? "No meetings" : `${p.rate}%`,
      label: `Week of ${day(p.week)}${p.inProgress ? " (so far)" : ""} · ${p.detail}`,
      key: LINE,
    })
  }

  return (
    <div ref={ref} className="relative w-full min-w-0">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={label}
        className="block overflow-visible"
        onPointerLeave={() => {
          setHover(null)
          setTip(null)
        }}
        onPointerMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect()
          const px = e.clientX - box.left
          const i = Math.round(((px - m.left) / Math.max(w, 1)) * (points.length - 1))
          show(Math.min(points.length - 1, Math.max(0, i)), e.clientX, e.clientY)
        }}
      >
        {[0, 50, 100].map((v) => (
          <g key={v}>
            <line x1={m.left} x2={m.left + w} y1={y(v)} y2={y(v)} stroke={GRID} strokeWidth={1} />
            <text x={m.left - 8} y={y(v) + 4} textAnchor="end" className="tnum fill-muted-foreground text-xs">
              {v}%
            </text>
          </g>
        ))}
        {points.map((p, i) =>
          (i % tickEvery === 0 && points.length - 1 - i >= tickEvery) || i === points.length - 1 ? (
            <text key={p.week} x={x(i)} y={height - 8} textAnchor="middle" className="fill-muted-foreground text-xs">
              {day(p.week).replace(/^\w+ /, "")}
            </text>
          ) : null,
        )}
        {hover !== null ? (
          <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + h} stroke={GRID} strokeWidth={1} />
        ) : null}
        {segments.map((seg) => (
          <g key={seg[0]}>
            {seg.length > 1 ? (
              <path
                d={`M${x(seg[0])},${y(0)} ${seg.map((i) => `L${x(i)},${y(points[i].rate!)}`).join(" ")} L${x(seg.at(-1)!)},${y(0)}Z`}
                fill={LINE}
                opacity={0.08}
              />
            ) : null}
            <polyline
              points={seg.map((i) => `${x(i)},${y(points[i].rate!)}`).join(" ")}
              fill="none"
              stroke={LINE}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          </g>
        ))}
        {points.map((p, i) =>
          p.rate !== null && (i === hover || i === lastIndex || seg1(segments, i)) ? (
            <circle key={p.week} cx={x(i)} cy={y(p.rate)} r={4.5} fill={LINE} stroke="var(--card)" strokeWidth={2} />
          ) : null,
        )}
        {lastIndex !== undefined ? (
          <text
            x={x(lastIndex) + 9}
            y={y(points[lastIndex].rate!) + 4}
            className="tnum fill-foreground text-[13px] font-semibold"
          >
            {points[lastIndex].rate}%
          </text>
        ) : null}
        {/* Keyboard: each week is a focusable target with the same readout as hover. */}
        {points.map((p, i) => (
          <rect
            key={`hit-${p.week}`}
            x={x(i) - Math.max(w / Math.max(points.length - 1, 1) / 2, 12)}
            y={m.top}
            width={Math.max(w / Math.max(points.length - 1, 1), 24)}
            height={h}
            fill="transparent"
            role="img"
            tabIndex={0}
            aria-label={`Week of ${day(p.week)}: ${p.rate === null ? "no meetings" : `${p.rate}%`}`}
            onFocus={(e) => {
              const box = e.currentTarget.getBoundingClientRect()
              show(i, box.left + box.width / 2, box.top)
            }}
            onBlur={() => {
              setHover(null)
              setTip(null)
            }}
          />
        ))}
      </svg>
      <Tooltip tip={tip} />
    </div>
  )
}

/** A week standing alone (no neighbours with data) still needs a dot to be seen. */
function seg1(segments: number[][], i: number) {
  return segments.some((s) => s.length === 1 && s[0] === i)
}

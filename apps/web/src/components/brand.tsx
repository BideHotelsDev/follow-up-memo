import { cn } from "@/lib/utils"

/**
 * bide brand marks.
 *
 * The real wordmark uses TT Ramillas with custom 22-degree flares on the letter
 * terminals. That face is licensed and not redistributable, so this sets the
 * wordmark in Fraunces — the closest available serif with the same short-serif,
 * modulated character. Replace with the supplied logo asset when it's to hand;
 * everything else here is drawn to the guidelines.
 *
 * The name is always lowercase. It is a Scots Gaelic word, not an acronym.
 */

/**
 * The secondary mark: a Celtic spiral inside a location pin. The spiral carries
 * journeys and cycles of movement; the pin makes it read as a modern map marker.
 */
export function SpiralPin({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 40" className={className} fill="none" role="img" aria-label="bide">
      {/* Pin: a teardrop, rounded above and pointed below. */}
      <path d="M16 39C16 39 30 23.6 30 15A14 14 0 1 0 2 15c0 8.6 14 24 14 24Z" fill="currentColor" />
      {/* Celtic spiral, unwinding outward — drawn as a stroked path so it stays
          crisp down to the 24px minimum the guidelines set. */}
      <path
        d="M16 20.4a5.4 5.4 0 1 0-5.4-5.4 5.4 5.4 0 0 0 5.4 5.4 8 8 0 0 0 8-8"
        stroke="var(--sidebar)"
        strokeWidth="2.1"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

/** The 'b' monogram, for favicons and the tightest spaces. */
export function Monogram({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("flex items-center justify-center rounded-md bg-primary text-primary-foreground", className)}
    >
      <span className="font-display text-[0.95em] leading-none font-semibold">b</span>
    </span>
  )
}

export function Wordmark({ className, showTrademark = true }: { className?: string; showTrademark?: boolean }) {
  return (
    <span className={cn("font-display leading-none font-semibold tracking-tight lowercase", className)}>
      bide
      {showTrademark ? (
        // Positioned at x-height, per the guidelines.
        <sup className="ml-[0.15em] align-super text-[0.36em] font-normal tracking-normal">®</sup>
      ) : null}
    </span>
  )
}

/**
 * Wordmark plus the product name. Follow-up is an internal tool under the
 * bide master brand, so bide leads and the tool name sits quietly beneath it.
 */
export function BrandLockup({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <SpiralPin className="size-7 shrink-0 text-primary" />
      {!compact ? (
        <span className="leading-none">
          <Wordmark className="block text-lg" />
          <span className="mt-1 block eyebrow tracking-[0.16em] opacity-70">Follow-up</span>
        </span>
      ) : null}
    </span>
  )
}

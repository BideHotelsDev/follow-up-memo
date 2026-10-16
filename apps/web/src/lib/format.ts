/** Dates and times as Bide reads them: UK time, "Tue 13 Oct", "14:00". */

const TZ = "Europe/London"

const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: TZ })
const timeFmt = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ })
const longFmt = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: TZ })
const isoFmt = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: TZ })

/** A YYYY-MM-DD date (no time zone) as "Tue 13 Oct". */
export function day(iso: string | null | undefined): string {
  if (!iso) return "No date"
  return dayFmt.format(new Date(`${iso}T12:00:00Z`)).replace(",", "")
}

/** A moment's UK calendar date, YYYY-MM-DD. */
export function localDate(moment: string | null | undefined): string | null {
  return moment ? isoFmt.format(new Date(moment)) : null
}

export function time(moment: string | null | undefined): string {
  return moment ? timeFmt.format(new Date(moment)) : "—"
}

/** "Today", or the day, for a moment. */
export function dayOf(moment: string | null | undefined, today: string): string {
  const d = localDate(moment)
  return d === today ? "Today" : day(d)
}

export function longDay(iso: string): string {
  return longFmt.format(new Date(`${iso}T12:00:00Z`)).replace(",", "")
}

export function greeting(moment = new Date()): string {
  const hour = Number(
    new Intl.DateTimeFormat("en-GB", { hour: "numeric", hourCycle: "h23", timeZone: TZ }).format(moment),
  )
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"
}

export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n} ${n === 1 ? word : many}`
}

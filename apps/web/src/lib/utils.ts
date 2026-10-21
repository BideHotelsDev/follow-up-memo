import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import type { KeyboardEvent } from "react"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** ⌘/Ctrl+Enter runs `action`. For boxes people dictate into (Wispr Flow): plain Enter adds a line instead. */
export function onModEnter(action: () => void) {
  return (e: KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      action()
    }
  }
}

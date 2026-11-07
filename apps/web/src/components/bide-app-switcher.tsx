import { useEffect } from "react"

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "bide-app-switcher": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        current?: string
        hub?: string
        align?: "start" | "end"
      }
    }
  }
}

/** Bide Hub's list of every Bide system (a web component from the Hub's switcher.js), shown with Sign in with Bide. */
export function BideAppSwitcher({ hub, current }: { hub: string; current: string }) {
  useEffect(() => {
    const src = `${hub}/switcher.js`
    if (document.querySelector(`script[src="${src}"]`)) return
    const script = document.createElement("script")
    script.src = src
    script.defer = true
    document.head.appendChild(script)
  }, [hub])
  return <bide-app-switcher hub={hub} current={current} align="start" />
}

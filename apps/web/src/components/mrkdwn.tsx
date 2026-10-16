import { Fragment } from "react"

/** Slack's mrkdwn as the message will read: *bold*, _italic_ and <url|links>. Text only, never HTML. */
const TOKEN = /(<[^>|]+\|[^>]+>|\*[^*\n]+\*|_[^_\n]+_)/g

function inline(line: string) {
  return line.split(TOKEN).map((part, i) => {
    if (part.startsWith("<") && part.includes("|")) {
      const [url, label] = part.slice(1, -1).split("|")
      return (
        <a key={i} href={url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
          {label}
        </a>
      )
    }
    if (part.length > 2 && part.startsWith("*") && part.endsWith("*"))
      return <strong key={i}>{part.slice(1, -1)}</strong>
    if (part.length > 2 && part.startsWith("_") && part.endsWith("_")) return <em key={i}>{part.slice(1, -1)}</em>
    return <Fragment key={i}>{part}</Fragment>
  })
}

export function Mrkdwn({ text }: { text: string }) {
  return (
    <div className="space-y-1">
      {text.split("\n").map((line, i) =>
        line.trim() === "" ? (
          <div key={i} className="h-1" />
        ) : line.startsWith("• ") ? (
          <p key={i} className="pl-4 -indent-3">
            • {inline(line.slice(2))}
          </p>
        ) : (
          <p key={i}>{inline(line)}</p>
        ),
      )}
    </div>
  )
}

import { useState } from "react"
import { toast } from "sonner"

import { PageHead, SectionTitle, surface } from "@/components/page"
import { Button } from "@/components/ui/button"
import { useApp } from "@/hooks/use-app"
import type { AppSettings } from "@/lib/api"
import { every, listOf, minutes, plural } from "@/lib/format"
import { cn } from "@/lib/utils"

type Info = AppSettings["pipeline"] & { owner: string; properties: number; categories: number }

const steps = ({
  owner,
  poll_interval_minutes,
  quiet_minutes,
  properties,
  categories,
  channels,
  internal_domains,
}: Info) => [
  ["Gemini takes the notes.", "Nothing changes about how calls are run."],
  [
    `The app checks ${owner}’s Drive ${every(poll_interval_minutes)}.`,
    `It waits until Gemini hasn’t touched a note for ${minutes(quiet_minutes)}, and only picks up notes it hasn’t handled.`,
  ],
  [
    "Claude reads the notes with the Bide context.",
    `Who owns what, the ${plural(properties, "property", "properties")}, the ${plural(categories, "meeting category", "meeting categories")} and ${plural(channels, "Slack channel")}, and how ${owner}’s emails should sound.`,
  ],
  [
    "The app checks Claude’s work.",
    "An action has to quote the notes. Dates and email addresses have to come from the notes or the invite.",
  ],
  [
    "It drafts everything.",
    `A Gmail draft for people outside Bide${
      internal_domains.length
        ? ` (anyone not at ${listOf(
            internal_domains.map((d) => `@${d}`),
            "or",
          )})`
        : ""
    }, Slack messages for the team, and tasks, each tagged with its property and category.`,
  ],
  [`${owner} gets one Slack message.`, "A summary with links to the drafts and anything that needs an answer."],
]

const rules = ({ owner, skip_rules, sensitive_topics, raw_text_days }: Info) => [
  ["Drafts first", `Emails wait in Gmail. Team messages wait for ${owner}’s approval. Nothing is sent automatically.`],
  ["No guessing", `Owners and dates come from the notes. Gaps become questions for ${owner}.`],
  [
    `${owner}’s own rules`,
    `Claude also follows the instructions ${owner} writes in Admin, but they can’t make it add what the notes don’t say.`,
  ],
  [
    "Private calls skipped",
    skip_rules
      ? `Calls matching the ${plural(skip_rules, "rule")} on the skip list are never processed.`
      : "Titles and people added to the skip list are never processed.",
  ],
  [
    "Sensitive calls stay private",
    sensitive_topics.length
      ? `Calls about ${listOf(sensitive_topics, "or")} get no team messages.`
      : "Calls Claude marks sensitive get no team messages.",
  ],
  [
    "Notes kept briefly",
    `The text of the notes is deleted after ${plural(raw_text_days, "day")}. Drafts, tasks and the link to the notes stay.`,
  ],
]

const problems = ({ owner, max_attempts }: Info) => [
  ["A draft fails", `The meeting shows as partial on Today and the app tries again, up to ${max_attempts} times.`],
  ["The notes are thin", `Fewer drafts, and the summary to ${owner} says so.`],
  ["Gemini edits the notes later", `Nothing changes by itself. ${owner} can reprocess the meeting.`],
  ["Google or Slack disconnects", "Runs pause and Admin gets a Slack alert."],
]

/** Wispr Flow (David's dictation app) spells these right once they're in its Dictionary. */
function Dictation({ words }: { words: string[] }) {
  const [copied, setCopied] = useState(false)
  return (
    <section className="mt-10">
      <SectionTitle title="Dictating with Wispr Flow" />
      <div className={cn(surface, "grid gap-4 p-5 lg:grid-cols-[7fr_5fr] lg:gap-8")}>
        <div className="grid content-start gap-3 text-muted-foreground">
          <p>
            Wispr Flow types wherever the cursor is, so it works in every box here: answers to questions, and edits to
            email and Slack drafts. It works in Gmail too.
          </p>
          <p>
            Click into a box, hold Wispr’s dictation key and speak. On a phone, use the Wispr keyboard. Press{" "}
            <kbd className="rounded border bg-secondary px-1.5 font-sans text-xs text-foreground">⌘ Enter</kbd> (or{" "}
            <kbd className="rounded border bg-secondary px-1.5 font-sans text-xs text-foreground">Ctrl Enter</kbd>) to
            save. A plain Enter starts a new line.
          </p>
        </div>
        <div className="grid content-start gap-3">
          <p className="text-muted-foreground">
            Add these to Wispr’s <b className="font-medium text-foreground">Dictionary</b> so names come out spelled
            right:
          </p>
          <p className="text-foreground">{words.join(", ")}</p>
          <div>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(words.join("\n"))
                  setCopied(true)
                } catch {
                  toast.error("Couldn't copy. Select the names and copy them instead.")
                }
              }}
            >
              {copied ? "Copied" : "Copy the names"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}

export default function HowPage() {
  const app = useApp()
  const info: Info = {
    ...app.pipeline,
    owner: app.owner_name,
    properties: app.properties.length,
    categories: app.categories.filter((c) => c.is_active).length,
  }
  const words = [...new Set([...app.people, ...app.properties.map((p) => p.name), ...app.systems, "Bide"])]
  return (
    <>
      <PageHead
        title="How it works"
        lede="It runs on the tools Bide already uses: Google Meet, Drive, Gmail and Slack, with Claude reading the notes."
      />
      <div className="grid items-start gap-6 lg:grid-cols-[7fr_5fr]">
        <ol className={cn(surface, "divide-y p-5")}>
          {steps(info).map(([title, detail], i) => (
            <li key={title} className="grid grid-cols-[2.25rem_1fr] gap-3 py-4 first:pt-0 last:pb-0">
              <span className="font-display tnum text-xl text-attention-foreground dark:text-attention">{i + 1}</span>
              <div>
                <b className="font-medium text-foreground">{title}</b>{" "}
                <span className="text-muted-foreground">{detail}</span>
              </div>
            </li>
          ))}
        </ol>
        <div className="grid gap-4 sm:grid-cols-2">
          {rules(info).map(([title, detail]) => (
            <div key={title} className={cn(surface, "grid content-start gap-2 p-5")}>
              <h4 className="font-sans font-medium text-foreground">{title}</h4>
              <p className="text-muted-foreground">{detail}</p>
            </div>
          ))}
        </div>
      </div>
      <section className="mt-10">
        <SectionTitle title="When something goes wrong" />
        <ul className={cn(surface, "divide-y p-5")}>
          {problems(info).map(([title, detail]) => (
            <li key={title} className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[14rem_1fr] sm:gap-4">
              <b className="font-medium text-foreground">{title}</b>
              <span className="text-muted-foreground">{detail}</span>
            </li>
          ))}
        </ul>
      </section>
      <Dictation words={words} />
    </>
  )
}

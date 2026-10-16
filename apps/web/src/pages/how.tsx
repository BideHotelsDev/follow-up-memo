import { PageHead, SectionTitle, surface } from "@/components/page"
import { cn } from "@/lib/utils"

const STEPS: [string, string][] = [
  ["Gemini takes the notes.", "Nothing changes about how calls are run."],
  [
    "The app checks David’s Drive every 10 minutes.",
    "It waits until Gemini has finished writing, and only picks up notes it hasn’t handled.",
  ],
  [
    "Claude reads the notes with the Bide context.",
    "Who owns what, which properties and channels exist, and how David’s emails should sound.",
  ],
  [
    "The app checks Claude’s work.",
    "An action has to quote the notes. Dates and email addresses have to come from the notes or the invite.",
  ],
  [
    "It drafts everything.",
    "A Gmail draft for people outside Bide, Slack messages for the team, and tasks, each tagged with its property.",
  ],
  ["David gets one Slack message.", "A summary with links to the drafts and anything that needs his answer."],
]

const RULES: [string, string][] = [
  ["Drafts first", "Emails wait in Gmail. Team messages wait for David’s approval. Nothing is sent automatically."],
  ["No guessing", "Owners and dates come from the notes. Gaps become questions for David."],
  ["Private calls skipped", "Titles and attendees on the skip list are never processed."],
  ["Sensitive calls stay private", "Pricing, contracts, HR, legal or investor topics get no team messages."],
]

export default function HowPage() {
  return (
    <>
      <PageHead
        title="How it works"
        lede="It runs on the tools Bide already uses: Google Meet, Drive, Gmail and Slack, with Claude reading the notes."
      />
      <div className="grid items-start gap-6 lg:grid-cols-[7fr_5fr]">
        <ol className={cn(surface, "divide-y p-5")}>
          {STEPS.map(([title, detail], i) => (
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
          {RULES.map(([title, detail]) => (
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
          {[
            ["A draft fails", "The meeting shows as partial on Today and the next runs try again."],
            ["The notes are thin", "Fewer drafts, and the summary to David says so."],
            ["Gemini edits the notes later", "Nothing changes by itself. David can reprocess the meeting."],
            ["Google or Slack disconnects", "Runs pause and Admin gets a Slack alert."],
          ].map(([title, detail]) => (
            <li key={title} className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[14rem_1fr] sm:gap-4">
              <b className="font-medium text-foreground">{title}</b>
              <span className="text-muted-foreground">{detail}</span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

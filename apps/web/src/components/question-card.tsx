import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { HotelTags } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { api, HttpError, type AnswerIn, type Question } from "@/lib/api"
import { onModEnter } from "@/lib/utils"

const option =
  "rounded-full border border-attention/40 bg-card px-3 py-1 text-sm text-foreground hover:border-attention-foreground disabled:opacity-50"

/** One question for the owner, answered in place: pick an owner, set a date, or type an answer (FR-35). */
export function QuestionCard({ question }: { question: Question }) {
  const queryClient = useQueryClient()
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled: question.kind === "owner" })
  const [text, setText] = useState("")
  const [due, setDue] = useState("")
  const answer = useMutation({
    mutationFn: (body: AnswerIn) => api.answer(question.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries()
      toast.success("Saved. The task and its Slack drafts are updated.")
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "Couldn't save"),
  })

  return (
    <div className="space-y-2 border-t border-attention/20 px-5 py-4 first:border-t-0">
      <p className="text-foreground">{question.text}</p>
      <div className="flex flex-wrap items-center gap-2 text-sm text-attention-foreground dark:text-attention">
        <HotelTags properties={question.meeting.properties} />
        <span>{question.meeting.title}</span>
      </div>
      {question.kind === "owner" ? (
        <div className="flex flex-wrap gap-2 pt-1">
          {(people.data ?? [])
            .filter((p) => p.role !== "admin")
            .map((p) => (
              <button
                key={p.id}
                className={option}
                disabled={answer.isPending}
                onClick={() => answer.mutate({ owner_user_id: p.id })}
              >
                {p.name}
              </button>
            ))}
        </div>
      ) : question.kind === "due" ? (
        <form
          className="flex flex-wrap gap-2 pt-1"
          onSubmit={(e) => {
            e.preventDefault()
            answer.mutate({ due_date: due || null })
          }}
        >
          <Input
            type="date"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            className="w-auto bg-card"
            aria-label="Due date"
          />
          <Button type="submit" disabled={!due || answer.isPending}>
            Save date
          </Button>
          <button type="button" className={option} onClick={() => answer.mutate({ due_date: null })}>
            No date
          </button>
        </form>
      ) : (
        <form
          className="flex items-end gap-2 pt-1"
          onSubmit={(e) => {
            e.preventDefault()
            answer.mutate({ text })
          }}
        >
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onModEnter(() => text.trim() && !answer.isPending && answer.mutate({ text }))}
            rows={1}
            placeholder="Type or dictate your answer"
            className="min-h-9 bg-card"
            aria-label="Your answer"
            aria-keyshortcuts="Meta+Enter Control+Enter"
          />
          <Button type="submit" disabled={!text.trim() || answer.isPending}>
            Save
          </Button>
        </form>
      )}
    </div>
  )
}

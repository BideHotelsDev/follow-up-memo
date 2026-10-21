import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Play } from "lucide-react"
import { toast } from "sonner"

import { Empty, Loading, surface } from "@/components/page"
import { Status } from "@/components/tags"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, HttpError } from "@/lib/api"
import { day, localDate, time } from "@/lib/format"
import { cn } from "@/lib/utils"

const KIND = { reminder: "Reminder", weekly_digest: "Weekly digest" } as const

function Notices() {
  const { data } = useQuery({ queryKey: ["notices"], queryFn: api.notices, refetchInterval: 60_000 })
  if (!data?.length) return null
  return (
    <div className="space-y-2">
      <h3 className="font-sans text-base font-medium">Reminders and digests</h3>
      <div className={cn(surface, "overflow-x-auto")}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Sent</TableHead>
              <TableHead>What</TableHead>
              <TableHead>To</TableHead>
              <TableHead>Result</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((n) => (
              <TableRow key={n.id}>
                <TableCell className="tnum whitespace-nowrap">
                  {day(localDate(n.updated_at))} {time(n.updated_at)}
                </TableCell>
                <TableCell>{KIND[n.kind]}</TableCell>
                <TableCell>{n.person}</TableCell>
                <TableCell className="max-w-md whitespace-normal">
                  {n.status === "failed" ? (
                    <Status tone="late">{`${n.error ?? "Failed"} (tried ${n.attempts}×)`}</Status>
                  ) : (
                    <Status tone="done">Posted</Status>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default function RunsPage() {
  const queryClient = useQueryClient()
  const { data } = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 30_000 })
  const runNow = useMutation({
    mutationFn: api.runNow,
    onSuccess: (run) => {
      queryClient.invalidateQueries()
      toast.success(`Run finished: ${run.processed} processed`)
    },
    onError: (err) => toast.error(err instanceof HttpError ? err.message : "The run failed"),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground">
          Every polling run: notes found, processed, skipped and failed (newest first).
        </p>
        <Button onClick={() => runNow.mutate()} disabled={runNow.isPending}>
          <Play className="size-4" /> {runNow.isPending ? "Running…" : "Run now"}
        </Button>
      </div>
      {!data ? (
        <Loading />
      ) : data.length ? (
        <div className={cn(surface, "overflow-x-auto")}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Started</TableHead>
                <TableHead className="text-right">Found</TableHead>
                <TableHead className="text-right">Processed</TableHead>
                <TableHead className="text-right">Skipped</TableHead>
                <TableHead className="text-right">Failed</TableHead>
                <TableHead>Result</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="tnum whitespace-nowrap">
                    {day(localDate(r.started_at))} {time(r.started_at)}
                  </TableCell>
                  <TableCell className="tnum text-right">{r.found}</TableCell>
                  <TableCell className="tnum text-right">{r.processed}</TableCell>
                  <TableCell className="tnum text-right">{r.skipped}</TableCell>
                  <TableCell className="tnum text-right">{r.failed}</TableCell>
                  <TableCell className="max-w-md whitespace-normal">
                    {r.error ? <Status tone="late">{r.error}</Status> : <Status tone="done">OK</Status>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <Empty>No runs yet. The worker runs every few minutes, or use Run now.</Empty>
      )}
      <Notices />
    </div>
  )
}

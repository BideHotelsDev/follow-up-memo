import { Loader2 } from "lucide-react"
import { Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/app-shell"
import { Button } from "@/components/ui/button"
import { useMe } from "@/hooks/use-me"
import ChannelsPage from "@/pages/admin/channels"
import ConnectionsPage from "@/pages/admin/connections"
import AdminLayout from "@/pages/admin/layout"
import PeoplePage from "@/pages/admin/people"
import RunsPage from "@/pages/admin/runs"
import SettingsPage from "@/pages/admin/settings"
import SkipRulesPage from "@/pages/admin/skip-rules"
import EmailsPage from "@/pages/emails"
import HowPage from "@/pages/how"
import MeetingsPage from "@/pages/meetings"
import SignInPage from "@/pages/sign-in"
import SlackPage from "@/pages/slack"
import TasksPage from "@/pages/tasks"
import TodayPage from "@/pages/today"

export default function App() {
  const me = useMe()

  if (me.isPending) {
    return (
      <div className="flex min-h-dvh items-center justify-center" aria-busy>
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    )
  }
  if (me.isError) {
    // A server that can't answer is not the same as being signed out: sign-in needs the same server.
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <h1 className="text-xl">The server is having trouble</h1>
        <p className="max-w-md text-sm text-muted-foreground">It isn't something you did. Try again in a moment.</p>
        <Button onClick={() => me.refetch()}>Try again</Button>
      </div>
    )
  }
  if (!me.data) return <SignInPage />

  const reviewer = me.data.role !== "member"
  return (
    <Routes>
      <Route element={<AppShell me={me.data} />}>
        <Route index element={<TodayPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="how" element={<HowPage />} />
        {reviewer ? (
          <>
            <Route path="meetings" element={<MeetingsPage />} />
            <Route path="meetings/:id" element={<MeetingsPage />} />
            <Route path="emails" element={<EmailsPage />} />
            <Route path="slack" element={<SlackPage />} />
          </>
        ) : null}
        {me.data.role === "admin" ? (
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<Navigate to="connections" replace />} />
            <Route path="connections" element={<ConnectionsPage />} />
            <Route path="people" element={<PeoplePage />} />
            <Route path="channels" element={<ChannelsPage />} />
            <Route path="skip-rules" element={<SkipRulesPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="runs" element={<RunsPage />} />
          </Route>
        ) : null}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
